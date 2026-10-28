"""Data sources: a local CSV file and the public Remotive API.

Both return the same "raw" DataFrame (all text columns), so nothing downstream
depends on where the rows came from.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import pandas as pd

from market_intel.config import Settings
from market_intel.http_client import ApiError, request_json
from market_intel.logging_setup import LOGGER_NAME, log_event
from market_intel.normalize import normalize_text, parse_salary_text, strip_html

logger = logging.getLogger(f"{LOGGER_NAME}.sources")

RAW_COLUMNS = [
    "source_job_id", "title", "company", "location", "work_mode", "employment_type",
    "posted_date", "salary_min", "salary_max", "salary_currency", "salary_period",
    "description", "source_url",
]
REQUIRED_COLUMNS = ("title", "company", "posted_date", "description")
REMOTIVE_URL = "https://remotive.com/api/remote-jobs"


class SourceError(RuntimeError):
    """The data source could not be read or has the wrong shape."""


def load_csv(path: str | Path) -> pd.DataFrame:
    """Read a CSV as text. Structural problems fail the whole file with a clear message."""
    path = Path(path)
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except FileNotFoundError as exc:
        raise SourceError(f"CSV file not found: {path}") from exc
    except pd.errors.EmptyDataError as exc:
        raise SourceError(f"CSV file is empty: {path}") from exc
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        raise SourceError(f"CSV file is malformed or not UTF-8 ({path.name}): {exc}") from exc
    except OSError as exc:
        raise SourceError(f"cannot read CSV file {path}: {exc}") from exc

    frame.columns = [column.strip().lower() for column in frame.columns]
    missing = [column for column in REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise SourceError(f"CSV is missing required column(s): {', '.join(missing)}")
    unknown = [column for column in frame.columns if column not in RAW_COLUMNS]
    if unknown:
        log_event(logger, "csv_unknown_columns_ignored", logging.WARNING, columns=",".join(unknown))
    for column in RAW_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    log_event(logger, "csv_loaded", file=path.name, rows=len(frame))
    return frame[RAW_COLUMNS]


def _remotive_row(job: dict) -> dict:
    salary = parse_salary_text(str(job.get("salary") or ""))
    return {
        "source_job_id": str(job.get("id", "")),
        "title": str(job.get("title") or ""),
        "company": str(job.get("company_name") or ""),
        "location": str(job.get("candidate_required_location") or ""),
        "work_mode": "remote",  # every Remotive listing is a remote role
        "employment_type": str(job.get("job_type") or ""),
        "posted_date": str(job.get("publication_date") or ""),
        "salary_min": f"{salary[0]:.0f}" if salary else "",
        "salary_max": f"{salary[1]:.0f}" if salary else "",
        "salary_currency": "USD" if salary else "",
        "salary_period": "year" if salary else "",
        "description": strip_html(str(job.get("description") or "")),
        "source_url": str(job.get("url") or ""),
    }


def fetch_remotive(settings: Settings, *, category: str | None = None, search: str | None = None,
                   limit: int | None = None,
                   request: Callable[..., object] = request_json) -> pd.DataFrame:
    """Fetch remote jobs from Remotive's public API (no key; see docs for terms and rate limits)."""
    params: dict[str, str | int] = {"limit": limit or settings.remotive_limit}
    if category:
        params["category"] = category
    if search:
        params["search"] = search
    payload = request("GET", REMOTIVE_URL, params=params,
                      timeout=settings.http_timeout_seconds, max_retries=settings.http_max_retries)
    jobs = payload.get("jobs") if isinstance(payload, dict) else None
    if not isinstance(jobs, list):
        raise SourceError("Remotive response has an unexpected shape (no 'jobs' list)")

    rows = [_remotive_row(job) for job in jobs if isinstance(job, dict)]
    skipped = len(jobs) - len(rows)
    unparsed_salary = sum(1 for job, row in zip((j for j in jobs if isinstance(j, dict)), rows)
                          if normalize_text(str(job.get("salary") or "")) and not row["salary_min"])
    log_event(logger, "remotive_fetched", jobs=len(rows), skipped_non_objects=skipped,
              salary_text_not_parsed=unparsed_salary)
    return pd.DataFrame(rows, columns=RAW_COLUMNS)


__all__ = ["ApiError", "SourceError", "RAW_COLUMNS", "load_csv", "fetch_remotive"]
