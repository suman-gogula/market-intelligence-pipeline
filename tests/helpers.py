"""Shared builders and fakes for the test suite."""
from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from market_intel.database import Database
from market_intel.sources import RAW_COLUMNS

TODAY = date(2026, 10, 24)
LONG_DESCRIPTION = "We need an engineer who knows Python, SQL and Docker to build data pipelines."


def raw_row(**overrides) -> dict:
    row = {
        "source_job_id": "T-1", "title": "Data Engineer", "company": "Test Company",
        "location": "Austin, TX, United States", "work_mode": "hybrid",
        "employment_type": "full_time", "posted_date": "2026-09-01", "salary_min": "",
        "salary_max": "", "salary_currency": "", "salary_period": "",
        "description": LONG_DESCRIPTION, "source_url": "",
    }
    row.update(overrides)
    return row


def raw_frame(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows), columns=RAW_COLUMNS)


def memory_db() -> Database:
    return Database("sqlite:///:memory:").connect()


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, text="", bad_json=False):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._payload


class FakeSession:
    """Plays back queued responses or exceptions, one per request call."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def close(self):
        self.closed = True


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
