"""Environment-driven settings with up-front validation.

Real environment variables win over values in a local ``.env`` file. Blank
values are treated as unset, so an untouched ``.env.example`` copy is valid.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from typing import Mapping

from dotenv import load_dotenv

from market_intel.database import (DatabaseError, database_password, parse_database_url,
                                   redact_database_url)
from market_intel.paths import PROJECT_ROOT

DEFAULT_DATABASE_URL = "sqlite:///data/local/market_intel.db"
DEMO_DATABASE_URL = "sqlite:///data/local/demo.db"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
LOG_FORMATS = ("text", "json")
_MODEL_NAME = re.compile(r"[A-Za-z0-9._-]+")


class ConfigError(ValueError):
    """Raised with every problem found so they can all be fixed in one pass."""


@dataclass(frozen=True)
class Settings:
    database_url: str = field(repr=False)
    log_level: str = "INFO"
    log_format: str = "text"
    http_timeout_seconds: float = 10.0
    http_max_retries: int = 3
    remotive_limit: int = 50
    gemini_api_key: str = field(default="", repr=False)
    gemini_model: str = DEFAULT_GEMINI_MODEL
    gemini_max_jobs_per_run: int = 20
    gemini_min_interval_seconds: float = 6.0

    @property
    def ai_configured(self) -> bool:
        return bool(self.gemini_api_key)

    def secrets(self) -> list[str]:
        """Values that must never appear in logs or error messages."""
        return [value for value in (self.gemini_api_key, database_password(self.database_url)) if value]

    def describe(self) -> dict[str, str]:
        """Settings in a form that is safe to print."""
        return {
            "database_url": redact_database_url(self.database_url),
            "log_level": self.log_level,
            "log_format": self.log_format,
            "http_timeout_seconds": str(self.http_timeout_seconds),
            "http_max_retries": str(self.http_max_retries),
            "remotive_limit": str(self.remotive_limit),
            "gemini_api_key": "set" if self.gemini_api_key else "not set",
            "gemini_model": self.gemini_model,
            "gemini_max_jobs_per_run": str(self.gemini_max_jobs_per_run),
            "gemini_min_interval_seconds": str(self.gemini_min_interval_seconds),
        }

    def with_database_url(self, database_url: str) -> "Settings":
        return replace(self, database_url=database_url)


def _read(env: Mapping[str, str], name: str, default: str) -> str:
    value = env.get(name)
    return default if value is None or not value.strip() else value.strip()


def _number(env, name, default, kind, low, high, errors):
    raw = _read(env, name, str(default))
    try:
        value = kind(raw)
    except ValueError:
        errors.append(f"{name} must be a number, got {raw!r}")
        return default
    if not low <= value <= high:
        errors.append(f"{name} must be between {low} and {high}, got {value}")
        return default
    return value


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Build validated settings.

    Pass ``env`` in tests; otherwise the process environment is used after
    loading ``.env`` from the project root (without overriding real variables).
    """
    if env is None:
        load_dotenv(PROJECT_ROOT / ".env", override=False)
        env = os.environ
    errors: list[str] = []

    database_url = _read(env, "DATABASE_URL", DEFAULT_DATABASE_URL)
    try:
        parse_database_url(database_url)
    except DatabaseError as exc:
        errors.append(f"DATABASE_URL: {exc}")

    log_level = _read(env, "LOG_LEVEL", "INFO").upper()
    if log_level not in LOG_LEVELS:
        errors.append(f"LOG_LEVEL must be one of {', '.join(LOG_LEVELS)}, got {log_level!r}")
        log_level = "INFO"
    log_format = _read(env, "LOG_FORMAT", "text").lower()
    if log_format not in LOG_FORMATS:
        errors.append(f"LOG_FORMAT must be one of {', '.join(LOG_FORMATS)}, got {log_format!r}")
        log_format = "text"

    timeout = _number(env, "HTTP_TIMEOUT_SECONDS", 10.0, float, 1.0, 60.0, errors)
    retries = _number(env, "HTTP_MAX_RETRIES", 3, int, 0, 5, errors)
    remotive_limit = _number(env, "REMOTIVE_LIMIT", 50, int, 1, 200, errors)
    max_jobs = _number(env, "GEMINI_MAX_JOBS_PER_RUN", 20, int, 0, 100, errors)
    interval = _number(env, "GEMINI_MIN_INTERVAL_SECONDS", 6.0, float, 0.0, 60.0, errors)

    gemini_key = _read(env, "GEMINI_API_KEY", "")
    if gemini_key and (len(gemini_key) < 16 or re.search(r"\s", gemini_key)):
        errors.append("GEMINI_API_KEY does not look like an API key (too short or contains spaces); "
                      "leave it empty to run without AI")
        gemini_key = ""
    gemini_model = _read(env, "GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    if not _MODEL_NAME.fullmatch(gemini_model):
        errors.append("GEMINI_MODEL may only contain letters, digits, '.', '_' and '-'")
        gemini_model = DEFAULT_GEMINI_MODEL

    if errors:
        raise ConfigError("Invalid configuration:\n  - " + "\n  - ".join(errors))
    return Settings(database_url=database_url, log_level=log_level, log_format=log_format,
                    http_timeout_seconds=timeout, http_max_retries=retries,
                    remotive_limit=remotive_limit, gemini_api_key=gemini_key,
                    gemini_model=gemini_model, gemini_max_jobs_per_run=max_jobs,
                    gemini_min_interval_seconds=interval)
