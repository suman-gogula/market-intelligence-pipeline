"""Thin database layer over sqlite3 (local/demo) and psycopg 3 (PostgreSQL).

All SQL in this project is written once, with ``:name`` placeholders and the
common subset of SQLite and PostgreSQL syntax. For PostgreSQL the placeholders
are rewritten to psycopg's ``%(name)s`` style at execution time. Values are
always bound as parameters, never formatted into SQL text.
"""
from __future__ import annotations

import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence
from urllib.parse import unquote, urlsplit

import pandas as pd

from market_intel.paths import SCHEMA_PATH, resolve_path

_NAMED_PARAM = re.compile(r"(?<!:):([A-Za-z_][A-Za-z0-9_]*)")
_QUERY_SECRET = re.compile(r"(?i)\b(password|sslpassword)=[^&\s]+")


class DatabaseError(RuntimeError):
    """Connection or setup problem with a user-actionable message."""


@dataclass(frozen=True)
class DatabaseTarget:
    kind: str  # "sqlite" or "postgresql"
    location: str  # file path (or ":memory:") for sqlite, full URL for PostgreSQL


def parse_database_url(url: str) -> DatabaseTarget:
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme == "sqlite":
        if parts.netloc:
            raise DatabaseError("sqlite URLs look like sqlite:///relative/path.db "
                                "or sqlite:////absolute/path.db")
        # urlsplit keeps the slash that follows the empty host; drop exactly one.
        path = unquote(parts.path)[1:]
        if not path:
            raise DatabaseError("sqlite URL has no file path (use sqlite:///data/local/app.db)")
        return DatabaseTarget("sqlite", path)
    if scheme in ("postgresql", "postgres"):
        if not parts.hostname:
            raise DatabaseError("PostgreSQL URL needs a host: "
                                "postgresql://user:password@host:5432/dbname")
        return DatabaseTarget("postgresql", url.strip())
    raise DatabaseError(f"unsupported database scheme {scheme!r}; use sqlite:// or postgresql://")


def redact_database_url(url: str) -> str:
    """Return the URL with any password masked, safe for logs and screens."""
    url = _QUERY_SECRET.sub(r"\1=***", url)
    parts = urlsplit(url)
    if "@" not in parts.netloc:
        return url
    userinfo, host = parts.netloc.rsplit("@", 1)
    user = userinfo.split(":", 1)[0]
    return parts._replace(netloc=f"{user}:***@{host}").geturl()


def database_password(url: str) -> str:
    try:
        return urlsplit(url).password or ""
    except ValueError:
        return ""


def _to_psycopg(sql: str) -> str:
    return _NAMED_PARAM.sub(r"%(\1)s", sql.replace("%", "%%"))


def split_statements(script: str) -> list[str]:
    """Split a schema script on semicolons (the schema file never embeds them in strings)."""
    return [statement.strip() for statement in script.split(";") if statement.strip()]


def to_python(value: Any) -> Any:
    """Convert pandas/numpy scalars (and missing values) to plain DB-bindable types."""
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value != value:  # NaN
        return None
    if value is pd.NA or value is pd.NaT:
        return None
    return value


class Database:
    def __init__(self, url: str):
        self.target = parse_database_url(url)
        self._conn: Any = None

    @property
    def kind(self) -> str:
        return self.target.kind

    def connect(self) -> "Database":
        if self._conn is not None:
            return self
        if self.kind == "sqlite":
            self._conn = self._connect_sqlite()
        else:
            self._conn = self._connect_postgres()
        return self

    def _connect_sqlite(self) -> sqlite3.Connection:
        location = self.target.location
        if location != ":memory:":
            path = resolve_path(location)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise DatabaseError(f"cannot create folder for database file {path.parent}: {exc}") from exc
            location = str(path)
        try:
            conn = sqlite3.connect(location, timeout=10)
        except sqlite3.Error as exc:
            raise DatabaseError(f"cannot open SQLite database {location}: {exc}") from exc
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _connect_postgres(self):
        try:
            import psycopg
        except ImportError as exc:
            raise DatabaseError("PostgreSQL support needs the optional driver: "
                                "pip install -r requirements-postgres.txt") from exc
        try:
            return psycopg.connect(self.target.location, connect_timeout=10)
        except psycopg.Error as exc:
            # The message from libpq does not include the password, but only
            # the exception type is surfaced to keep that guarantee simple.
            raise DatabaseError(f"cannot connect to PostgreSQL ({type(exc).__name__}); "
                                "check DATABASE_URL, network access and SSL settings") from exc

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "Database":
        return self.connect()

    def __exit__(self, *exc_info) -> None:
        self.close()

    def _cursor(self):
        if self._conn is None:
            raise DatabaseError("database is not connected")
        return self._conn.cursor()

    def _prepare(self, sql: str, params: Mapping[str, Any] | None) -> str:
        if params is not None and self.kind == "postgresql":
            return _to_psycopg(sql)
        return sql

    def execute(self, sql: str, params: Mapping[str, Any] | None = None) -> int:
        """Run one statement and return the affected row count."""
        cursor = self._cursor()
        try:
            statement = self._prepare(sql, params)
            if params is None:
                cursor.execute(statement)
            else:
                cursor.execute(statement, params)
            return cursor.rowcount
        finally:
            cursor.close()

    def executemany(self, sql: str, rows: Sequence[Mapping[str, Any]]) -> None:
        if not rows:
            return
        cursor = self._cursor()
        try:
            cursor.executemany(self._prepare(sql, rows[0]), list(rows))
        finally:
            cursor.close()

    def query(self, sql: str, params: Mapping[str, Any] | None = None) -> pd.DataFrame:
        cursor = self._cursor()
        try:
            statement = self._prepare(sql, params)
            if params is None:
                cursor.execute(statement)
            else:
                cursor.execute(statement, params)
            columns = [column[0] for column in cursor.description]
            return pd.DataFrame(cursor.fetchall(), columns=columns)
        finally:
            cursor.close()

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    @contextmanager
    def transaction(self) -> Iterator["Database"]:
        """Commit on success, roll back everything on any exception."""
        try:
            yield self
        except BaseException:
            self.rollback()
            raise
        else:
            self.commit()

    def init_schema(self, schema_path: Path = SCHEMA_PATH) -> None:
        """Create tables and indexes if missing (idempotent)."""
        script = schema_path.read_text(encoding="utf-8")
        with self.transaction():
            for statement in split_statements(script):
                self.execute(statement)
