"""Run the analytical SQL files and export their results as CSV for BI tools."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from market_intel.database import Database
from market_intel.logging_setup import LOGGER_NAME, log_event
from market_intel.paths import QUERIES_DIR

logger = logging.getLogger(f"{LOGGER_NAME}.reports")

EXPORT_NOTE = """Exported by `python -m market_intel report`.

Every analytical file carries a data_origin column:
  sample    synthetic demo data generated for this repository
  user_csv  rows from a CSV file supplied by the person running the pipeline
  live      rows fetched from a live API (see docs/data-sources.md for terms)

Do not mix origins in one chart without filtering on data_origin.
"""


def list_queries(queries_dir: Path = QUERIES_DIR) -> list[Path]:
    return sorted(queries_dir.glob("*.sql"))


def run_query(db: Database, name: str, queries_dir: Path = QUERIES_DIR) -> pd.DataFrame:
    return db.query((queries_dir / f"{name}.sql").read_text(encoding="utf-8"))


def export_reports(db: Database, output_dir: Path, queries_dir: Path = QUERIES_DIR) -> dict[str, int]:
    """Write one CSV per query file and return {file stem: row count}."""
    output_dir.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for query_file in list_queries(queries_dir):
        frame = db.query(query_file.read_text(encoding="utf-8"))
        frame.to_csv(output_dir / f"{query_file.stem}.csv", index=False, encoding="utf-8")
        counts[query_file.stem] = len(frame)
    (output_dir / "EXPORT_NOTE.txt").write_text(EXPORT_NOTE, encoding="utf-8")
    log_event(logger, "reports_exported", directory=output_dir.name, files=len(counts))
    return counts
