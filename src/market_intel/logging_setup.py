"""Structured logging with secret redaction.

Every record is emitted as an event name plus key/value fields, either as a
readable text line or as one JSON object per line (LOG_FORMAT=json).
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Iterable

LOGGER_NAME = "market_intel"
_MIN_SECRET_LENGTH = 4


def redact(text: str, secrets: Iterable[str]) -> str:
    for secret in secrets:
        if secret and len(secret) >= _MIN_SECRET_LENGTH:
            text = text.replace(secret, "***")
    return text


class RedactingFilter(logging.Filter):
    """Masks registered secrets in the message and in structured fields."""

    def __init__(self, secrets: Iterable[str]):
        super().__init__()
        self._secrets = tuple(secrets)

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage(), self._secrets)
        record.args = ()
        fields = getattr(record, "fields", {})
        record.fields = {key: redact(value, self._secrets) if isinstance(value, str) else value
                         for key, value in fields.items()}
        return True


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        pairs = " ".join(f"{key}={value}" for key, value in getattr(record, "fields", {}).items())
        line = f"{timestamp} {record.levelname:<7} {record.name} {record.msg} {pairs}".rstrip()
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="seconds"),
            "level": record.levelname,
            "logger": record.name,
            "event": record.msg,
            **getattr(record, "fields", {}),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(level: str = "INFO", log_format: str = "text",
                      secrets: Iterable[str] = (), stream=None) -> logging.Logger:
    """Attach a single redacting handler to the package logger (safe to call repeatedly)."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter() if log_format == "json" else TextFormatter())
    handler.addFilter(RedactingFilter(secrets))
    logger.addHandler(handler)
    return logger


def log_event(logger: logging.Logger, event: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, event, extra={"fields": fields})
