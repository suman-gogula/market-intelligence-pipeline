"""HTTP JSON helper with timeouts and bounded, polite retries."""
from __future__ import annotations

import logging
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import requests

from market_intel.logging_setup import LOGGER_NAME, log_event

logger = logging.getLogger(f"{LOGGER_NAME}.http")

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_BODY_SNIPPET_CHARS = 200


class ApiError(RuntimeError):
    """An external API call failed in a way the caller should handle."""


def _retry_delay(response, attempt: int, backoff_base: float, max_backoff: float) -> float:
    retry_after = response.headers.get("Retry-After") if response is not None else None
    if retry_after and str(retry_after).isdigit():
        return min(float(retry_after), max_backoff)
    return min(backoff_base * (2 ** attempt), max_backoff)


def request_json(method: str, url: str, *, timeout: float, max_retries: int,
                 headers: dict | None = None, params: dict | None = None,
                 json_body: Any = None, session: requests.Session | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 backoff_base: float = 1.0, max_backoff: float = 20.0) -> Any:
    """Call an API and return decoded JSON.

    Retries only transient failures (timeouts, connection errors, 429 and 5xx),
    at most ``max_retries`` times, so total attempts are ``max_retries + 1``.
    Query strings are never logged because some APIs carry keys there.
    """
    parts = urlsplit(url)
    label = f"{method} {parts.netloc}{parts.path}"
    own_session = session is None
    session = session or requests.Session()
    try:
        for attempt in range(max_retries + 1):
            is_last_attempt = attempt == max_retries
            try:
                response = session.request(method, url, headers=headers, params=params,
                                            json=json_body, timeout=timeout)
            except (requests.Timeout, requests.ConnectionError) as exc:
                if is_last_attempt:
                    raise ApiError(f"{label} failed after {attempt + 1} attempt(s): "
                                   f"{type(exc).__name__}") from exc
                delay = _retry_delay(None, attempt, backoff_base, max_backoff)
                log_event(logger, "http_retry", logging.WARNING, target=label,
                          attempt=attempt + 1, reason=type(exc).__name__, wait_seconds=delay)
                sleep(delay)
                continue
            except requests.RequestException as exc:
                raise ApiError(f"{label} failed: {type(exc).__name__}") from exc

            if response.status_code in RETRYABLE_STATUS and not is_last_attempt:
                delay = _retry_delay(response, attempt, backoff_base, max_backoff)
                log_event(logger, "http_retry", logging.WARNING, target=label,
                          attempt=attempt + 1, reason=f"status_{response.status_code}",
                          wait_seconds=delay)
                sleep(delay)
                continue
            if response.status_code >= 400:
                snippet = (response.text or "")[:_BODY_SNIPPET_CHARS]
                raise ApiError(f"{label} returned HTTP {response.status_code}: {snippet}")
            try:
                return response.json()
            except ValueError as exc:
                raise ApiError(f"{label} returned a body that is not valid JSON") from exc
        raise ApiError(f"{label} failed")  # unreachable when max_retries >= 0
    finally:
        if own_session:
            session.close()
