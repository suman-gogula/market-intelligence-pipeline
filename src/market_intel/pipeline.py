"""End-to-end run: load -> validate -> clean -> store, with an audit row per run."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable, Sequence

import pandas as pd

from market_intel.clean import clean_jobs
from market_intel.database import Database, to_python
from market_intel.enrich import DEFAULT_ORIGINS, Classifier, enrich_pending
from market_intel.logging_setup import LOGGER_NAME, log_event
from market_intel.skills import CATALOG
from market_intel.validate import validate_rows

logger = logging.getLogger(f"{LOGGER_NAME}.pipeline")

DATA_ORIGINS = ("sample", "live", "user_csv")

_INSERT_JOB = """
INSERT INTO job_postings (
    job_id, content_hash, source_name, data_origin, source_job_id, source_url, title,
    title_normalized, company, location_raw, city, country, work_mode, employment_type,
    posted_date, salary_currency, salary_annual_min, salary_annual_max, description,
    first_run_id, ingested_at
) VALUES (
    :job_id, :content_hash, :source_name, :data_origin, :source_job_id, :source_url, :title,
    :title_normalized, :company, :location_raw, :city, :country, :work_mode, :employment_type,
    :posted_date, :salary_currency, :salary_annual_min, :salary_annual_max, :description,
    :first_run_id, :ingested_at
) ON CONFLICT DO NOTHING
"""


class PipelineError(RuntimeError):
    def __init__(self, message: str, run_id: str):
        super().__init__(message)
        self.run_id = run_id


@dataclass
class RunSummary:
    run_id: str
    source_name: str
    data_origin: str
    rows_read: int = 0
    rows_rejected: int = 0
    rows_duplicate_in_batch: int = 0
    rows_inserted: int = 0
    rows_already_stored: int = 0
    ai_enriched: int = 0
    ai_failed: int = 0


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def _records(frame: pd.DataFrame) -> list[dict]:
    return [{key: to_python(value) for key, value in row.items()} for row in frame.to_dict("records")]


def _seed_skill_catalog(db: Database) -> None:
    db.executemany(
        "INSERT INTO skill_catalog (skill, category) VALUES (:skill, :category) "
        "ON CONFLICT (skill) DO UPDATE SET category = excluded.category",
        [{"skill": skill.name, "category": skill.category} for skill in CATALOG])


def _store(db: Database, summary: RunSummary, raw: pd.DataFrame, today: date | None) -> None:
    """All database writes for one run happen in the caller's single transaction."""
    summary.rows_read = len(raw)
    checked = validate_rows(raw, today)
    cleaned = clean_jobs(checked.valid, source_name=summary.source_name,
                         data_origin=summary.data_origin)
    summary.rows_rejected = len(checked.rejected)
    summary.rows_duplicate_in_batch = cleaned.duplicates_in_batch

    ingested_at = _utc_now()
    inserted_ids: set[str] = set()
    for job in _records(cleaned.jobs):
        job.update(first_run_id=summary.run_id, ingested_at=ingested_at)
        # DO NOTHING covers both unique keys (job_id and content_hash): 0 rows means "seen before".
        if db.execute(_INSERT_JOB, job) == 1:
            inserted_ids.add(job["job_id"])
    summary.rows_inserted = len(inserted_ids)
    summary.rows_already_stored = len(cleaned.jobs) - len(inserted_ids)

    new_skills = cleaned.skills[cleaned.skills["job_id"].isin(inserted_ids)]
    db.executemany("INSERT INTO job_skills (job_id, skill) VALUES (:job_id, :skill) "
                   "ON CONFLICT DO NOTHING", _records(new_skills))
    db.executemany(
        "INSERT INTO rejected_records (run_id, row_number, reason, raw_record) "
        "VALUES (:run_id, :row_number, :reason, :raw_record)",
        [{**row, "run_id": summary.run_id} for row in _records(checked.rejected)])
    db.execute(
        "UPDATE pipeline_runs SET status = 'succeeded', finished_at = :finished_at, "
        "rows_read = :rows_read, rows_rejected = :rows_rejected, "
        "rows_duplicate_in_batch = :dup, rows_inserted = :inserted, "
        "rows_already_stored = :stored WHERE run_id = :run_id",
        {"finished_at": _utc_now(), "rows_read": summary.rows_read,
         "rows_rejected": summary.rows_rejected, "dup": summary.rows_duplicate_in_batch,
         "inserted": summary.rows_inserted, "stored": summary.rows_already_stored,
         "run_id": summary.run_id})


def run_pipeline(db: Database, *, source_name: str, data_origin: str,
                 load: Callable[[], pd.DataFrame], classifier: Classifier | None = None,
                 ai_max_jobs: int = 0, ai_origins: Sequence[str] = DEFAULT_ORIGINS,
                 today: date | None = None) -> RunSummary:
    """Run the pipeline once. Re-running with the same input stores nothing new.

    The run row is committed first, so a failed run is still visible afterwards.
    Data writes and the "succeeded" status commit together or not at all.
    """
    if data_origin not in DATA_ORIGINS:
        raise ValueError(f"data_origin must be one of {DATA_ORIGINS}, got {data_origin!r}")
    db.init_schema()
    summary = RunSummary(run_id=_new_run_id(), source_name=source_name, data_origin=data_origin)
    with db.transaction():
        _seed_skill_catalog(db)
        db.execute("INSERT INTO pipeline_runs (run_id, source_name, data_origin, status, started_at) "
                   "VALUES (:run_id, :source_name, :data_origin, 'running', :started_at)",
                   {"run_id": summary.run_id, "source_name": source_name,
                    "data_origin": data_origin, "started_at": _utc_now()})
    log_event(logger, "run_started", run_id=summary.run_id, source=source_name, origin=data_origin)

    try:
        raw = load()
        with db.transaction():
            _store(db, summary, raw, today)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:500]
        with db.transaction():
            db.execute("UPDATE pipeline_runs SET status = 'failed', finished_at = :finished_at, "
                       "error_message = :message WHERE run_id = :run_id",
                       {"finished_at": _utc_now(), "message": message, "run_id": summary.run_id})
        log_event(logger, "run_failed", logging.ERROR, run_id=summary.run_id, error=message)
        raise PipelineError(str(exc), summary.run_id) from exc

    if classifier is not None and ai_max_jobs > 0:
        try:
            outcome = enrich_pending(db, classifier, ai_max_jobs, ai_origins)
            summary.ai_enriched, summary.ai_failed = outcome.enriched, outcome.failed
            with db.transaction():
                db.execute("UPDATE pipeline_runs SET ai_enriched = :count WHERE run_id = :run_id",
                           {"count": outcome.enriched, "run_id": summary.run_id})
        except Exception as exc:  # AI is optional: the stored data is already committed
            log_event(logger, "ai_enrichment_aborted", logging.WARNING,
                      error=f"{type(exc).__name__}: {exc}")

    log_event(logger, "run_finished", run_id=summary.run_id, read=summary.rows_read,
              rejected=summary.rows_rejected, duplicates_in_batch=summary.rows_duplicate_in_batch,
              inserted=summary.rows_inserted, already_stored=summary.rows_already_stored,
              ai_enriched=summary.ai_enriched)
    return summary
