"""Apply optional AI labels to stored postings without ever blocking ingestion."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, Sequence

from market_intel.database import Database
from market_intel.gemini import AiError, Classification
from market_intel.logging_setup import LOGGER_NAME, log_event

logger = logging.getLogger(f"{LOGGER_NAME}.enrich")

# Stop calling the API after this many failures in a row (bad key, quota, outage).
MAX_CONSECUTIVE_FAILURES = 3
DEFAULT_ORIGINS = ("sample", "user_csv")  # live data is excluded unless explicitly requested


class Classifier(Protocol):
    model: str

    def classify(self, title: str, description: str) -> Classification: ...


@dataclass
class EnrichmentResult:
    enriched: int = 0
    failed: int = 0
    stopped_early: bool = False


def enrich_pending(db: Database, classifier: Classifier, max_jobs: int,
                   origins: Sequence[str] = DEFAULT_ORIGINS) -> EnrichmentResult:
    """Classify up to ``max_jobs`` postings that have no AI label yet.

    Each success is committed immediately, so an interruption keeps earlier work
    and the next run continues where this one stopped.
    """
    result = EnrichmentResult()
    if max_jobs <= 0 or not origins:
        return result
    placeholders = ", ".join(f":origin_{index}" for index in range(len(origins)))
    params = {f"origin_{index}": origin for index, origin in enumerate(origins)}
    params["limit"] = max_jobs
    pending = db.query(
        "SELECT job_id, title, description FROM job_postings "
        f"WHERE ai_category IS NULL AND data_origin IN ({placeholders}) "
        "ORDER BY posted_date DESC, job_id LIMIT :limit", params)

    consecutive_failures = 0
    for job in pending.to_dict("records"):
        try:
            label = classifier.classify(job["title"], job["description"])
        except AiError as exc:
            result.failed += 1
            consecutive_failures += 1
            log_event(logger, "ai_job_failed", logging.WARNING, job_id=job["job_id"], error=str(exc))
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                result.stopped_early = True
                log_event(logger, "ai_enrichment_stopped", logging.WARNING,
                          reason="too_many_consecutive_failures")
                break
            continue
        consecutive_failures = 0
        with db.transaction():
            db.execute(
                "UPDATE job_postings SET ai_category = :category, ai_summary = :summary, "
                "ai_model = :model, ai_enriched_at = :enriched_at WHERE job_id = :job_id",
                {"category": label.category, "summary": label.summary, "model": classifier.model,
                 "enriched_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                 "job_id": job["job_id"]})
        result.enriched += 1
    log_event(logger, "ai_enrichment_finished", enriched=result.enriched, failed=result.failed,
              stopped_early=result.stopped_early)
    return result
