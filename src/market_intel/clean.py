"""Normalisation, duplicate removal and skill extraction for validated rows."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Mapping

import pandas as pd

from market_intel.normalize import (annualize, normalize_employment_type, normalize_key,
                                    normalize_text, normalize_work_mode, parse_amount,
                                    parse_iso_date, parse_location)
from market_intel.skills import extract_skills

MAX_DESCRIPTION_CHARS = 20_000

JOB_COLUMNS = [
    "job_id", "content_hash", "source_name", "data_origin", "source_job_id", "source_url",
    "title", "title_normalized", "company", "location_raw", "city", "country", "work_mode",
    "employment_type", "posted_date", "salary_currency", "salary_annual_min",
    "salary_annual_max", "description",
]
SKILL_COLUMNS = ["job_id", "skill"]


@dataclass
class CleanResult:
    jobs: pd.DataFrame
    skills: pd.DataFrame
    duplicates_in_batch: int


def stable_hash(*parts: str) -> str:
    # The unit separator cannot appear in normalised text, so parts never blur together.
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:32]


def _salary_fields(row: Mapping[str, str]) -> tuple[str | None, float | None, float | None]:
    low_text = normalize_text(row.get("salary_min"))
    if not low_text:
        return None, None, None
    period = normalize_text(row["salary_period"]).lower()
    low = annualize(parse_amount(low_text), period)
    high = annualize(parse_amount(normalize_text(row["salary_max"])), period)
    return normalize_text(row["salary_currency"]).upper(), low, high


def _build_job(row: Mapping[str, str], source_name: str, data_origin: str) -> dict:
    title = normalize_text(row["title"])
    company = normalize_text(row["company"])
    location_raw = normalize_text(row.get("location"))
    city, country = parse_location(location_raw)
    posted = parse_iso_date(row["posted_date"]).isoformat()
    currency, salary_low, salary_high = _salary_fields(row)
    source_job_id = normalize_text(row.get("source_job_id"))

    # The content hash identifies "the same listing" across sources and re-posts of
    # the same day, ignoring case, spacing and punctuation differences.
    content_hash = stable_hash(normalize_key(title), normalize_key(company),
                               normalize_key(city), normalize_key(country), posted)
    job_id = stable_hash(source_name, source_job_id) if source_job_id else content_hash
    return {
        "job_id": job_id,
        "content_hash": content_hash,
        "source_name": source_name,
        "data_origin": data_origin,
        "source_job_id": source_job_id or None,
        "source_url": normalize_text(row.get("source_url")) or None,
        "title": title,
        "title_normalized": normalize_key(title),
        "company": company,
        "location_raw": location_raw or None,
        "city": city,
        "country": country,
        "work_mode": normalize_work_mode(row.get("work_mode"), location_raw),
        "employment_type": normalize_employment_type(row.get("employment_type")),
        "posted_date": posted,
        "salary_currency": currency,
        "salary_annual_min": salary_low,
        "salary_annual_max": salary_high,
        "description": normalize_text(row["description"])[:MAX_DESCRIPTION_CHARS],
    }


def clean_jobs(valid: pd.DataFrame, *, source_name: str, data_origin: str) -> CleanResult:
    records = [_build_job(row, source_name, data_origin) for row in valid.to_dict("records")]
    jobs = pd.DataFrame(records, columns=JOB_COLUMNS)
    before = len(jobs)
    jobs = jobs.drop_duplicates(subset="job_id", keep="first")
    jobs = jobs.drop_duplicates(subset="content_hash", keep="first").reset_index(drop=True)

    skill_rows = [{"job_id": job["job_id"], "skill": skill}
                  for job in jobs.to_dict("records")
                  for skill in extract_skills(f"{job['title']} {job['description']}")]
    skills = pd.DataFrame(skill_rows, columns=SKILL_COLUMNS)
    return CleanResult(jobs=jobs, skills=skills, duplicates_in_batch=before - len(jobs))
