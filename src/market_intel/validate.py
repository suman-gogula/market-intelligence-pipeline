"""Row-level validation. Bad rows are rejected with reasons, never silently fixed."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping

import pandas as pd

from market_intel.normalize import (PERIOD_TO_ANNUAL_FACTOR, annualize, normalize_text,
                                    parse_amount, parse_iso_date)

REQUIRED_TEXT_FIELDS = ("title", "company", "description", "posted_date")
MIN_DESCRIPTION_CHARS = 30
MAX_TITLE_CHARS = 300
MAX_COMPANY_CHARS = 200
MIN_ANNUAL_SALARY = 1_000
MAX_ANNUAL_SALARY = 100_000_000
_RAW_RECORD_DESCRIPTION_CHARS = 300


@dataclass
class ValidationResult:
    valid: pd.DataFrame  # original columns plus row_number
    rejected: pd.DataFrame  # row_number, reason, raw_record


def _salary_problems(row: Mapping[str, str]) -> list[str]:
    low_text = normalize_text(row.get("salary_min"))
    high_text = normalize_text(row.get("salary_max"))
    if not low_text and not high_text:
        return []
    if not low_text or not high_text:
        return ["salary_min and salary_max must both be present or both be empty"]

    problems: list[str] = []
    amounts = []
    for name, text in (("salary_min", low_text), ("salary_max", high_text)):
        try:
            amounts.append(parse_amount(text))
        except ValueError:
            problems.append(f"invalid {name}")
    if problems:
        return problems
    low, high = amounts
    if low > high:
        problems.append("salary_min is greater than salary_max")

    currency = normalize_text(row.get("salary_currency"))
    if not (len(currency) == 3 and currency.isalpha()):
        problems.append("salary_currency must be a 3-letter code")
    period = normalize_text(row.get("salary_period")).lower()
    if period not in PERIOD_TO_ANNUAL_FACTOR:
        problems.append(f"salary_period must be one of {', '.join(PERIOD_TO_ANNUAL_FACTOR)}")
    elif not problems:
        if not MIN_ANNUAL_SALARY <= annualize(low, period) <= MAX_ANNUAL_SALARY \
                or not MIN_ANNUAL_SALARY <= annualize(high, period) <= MAX_ANNUAL_SALARY:
            problems.append("annualised salary is outside the plausible range")
    return problems


def row_problems(row: Mapping[str, str], today: date) -> list[str]:
    problems = [f"missing {field}" for field in REQUIRED_TEXT_FIELDS
                if not normalize_text(row.get(field))]

    if len(normalize_text(row.get("title"))) > MAX_TITLE_CHARS:
        problems.append("title is too long")
    if len(normalize_text(row.get("company"))) > MAX_COMPANY_CHARS:
        problems.append("company is too long")
    description = normalize_text(row.get("description"))
    if description and len(description) < MIN_DESCRIPTION_CHARS:
        problems.append("description is too short to analyse")

    posted = normalize_text(row.get("posted_date"))
    if posted:
        try:
            if parse_iso_date(posted) > today + timedelta(days=1):
                problems.append("posted_date is in the future")
        except ValueError:
            problems.append("posted_date is not a valid YYYY-MM-DD date")

    problems.extend(_salary_problems(row))
    return problems


def _raw_record_json(row: Mapping[str, str]) -> str:
    shortened = dict(row)
    description = shortened.get("description", "")
    if len(description) > _RAW_RECORD_DESCRIPTION_CHARS:
        shortened["description"] = description[:_RAW_RECORD_DESCRIPTION_CHARS] + "..."
    return json.dumps(shortened, ensure_ascii=True)


def validate_rows(raw: pd.DataFrame, today: date | None = None) -> ValidationResult:
    """Split raw rows into valid and rejected. ``row_number`` counts data rows from 1."""
    today = today or date.today()
    valid_rows: list[dict] = []
    rejected_rows: list[dict] = []
    for row_number, row in enumerate(raw.to_dict("records"), start=1):
        problems = row_problems(row, today)
        if problems:
            rejected_rows.append({"row_number": row_number, "reason": "; ".join(problems),
                                  "raw_record": _raw_record_json(row)})
        else:
            valid_rows.append({"row_number": row_number, **row})
    valid = pd.DataFrame(valid_rows, columns=["row_number", *raw.columns])
    rejected = pd.DataFrame(rejected_rows, columns=["row_number", "reason", "raw_record"])
    return ValidationResult(valid=valid, rejected=rejected)
