"""Locations of code-adjacent resources (SQL files, sample data).

The project is meant to run from a checkout (or an editable install), so the
root is derived from this file's position rather than the working directory.
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = PROJECT_ROOT / "sql"
SCHEMA_PATH = SQL_DIR / "schema.sql"
QUERIES_DIR = SQL_DIR / "queries"
SAMPLE_CSV = PROJECT_ROOT / "data" / "sample" / "sample_jobs.csv"
SAMPLE_EXPORT_DIR = PROJECT_ROOT / "exports" / "sample"


def resolve_path(path: str | Path) -> Path:
    """Resolve relative paths against the project root, not the shell's cwd."""
    candidate = Path(path)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
