import unittest

import requests

from market_intel.http_client import ApiError, request_json
from tests.helpers import FakeResponse, FakeSession


def call(session, **kwargs):
    sleeps = []
    defaults = dict(timeout=5, max_retries=2, session=session, sleep=sleeps.append)
    result = request_json("GET", "https://api.example.com/v1/jobs?key=SECRET", **{**defaults, **kwargs})
    return result, sleeps


class RequestJsonTests(unittest.TestCase):
    def test_returns_json_and_passes_timeout(self):
        session = FakeSession(FakeResponse(payload={"ok": True}))
        result, sleeps = call(session)
        self.assertEqual(result, {"ok": True})
        self.assertEqual(sleeps, [])
        self.assertEqual(session.calls[0][2]["timeout"], 5)

    def test_retries_transient_status_then_succeeds_with_growing_waits(self):
        session = FakeSession(FakeResponse(503), FakeResponse(429), FakeResponse(payload=[1]))
        result, sleeps = call(session)
        self.assertEqual(result, [1])
        self.assertEqual(sleeps, [1.0, 2.0])

    def test_retry_after_header_is_honoured_but_capped(self):
        session = FakeSession(FakeResponse(429, headers={"Retry-After": "999"}), FakeResponse(payload={}))
        _, sleeps = call(session, max_backoff=7)
        self.assertEqual(sleeps, [7.0])

    def test_gives_up_after_bounded_attempts(self):
        session = FakeSession(FakeResponse(500), FakeResponse(500), FakeResponse(500, text="boom"))
        with self.assertRaises(ApiError) as caught:
            call(session)
        self.assertEqual(len(session.calls), 3)  # max_retries=2 means 3 attempts
        self.assertIn("HTTP 500", str(caught.exception))

    def test_client_errors_are_not_retried(self):
        session = FakeSession(FakeResponse(400, text="bad request"))
        with self.assertRaises(ApiError):
            call(session)
        self.assertEqual(len(session.calls), 1)

    def test_timeouts_are_retried_then_reported_without_url_query(self):
        session = FakeSession(requests.Timeout(), requests.ConnectionError(), requests.Timeout())
        with self.assertRaises(ApiError) as caught:
            call(session)
        self.assertIn("api.example.com/v1/jobs", str(caught.exception))
        self.assertNotIn("SECRET", str(caught.exception))

    def test_timeout_then_success(self):
        session = FakeSession(requests.Timeout(), FakeResponse(payload={"a": 1}))
        result, sleeps = call(session)
        self.assertEqual((result, len(sleeps)), ({"a": 1}, 1))

    def test_invalid_json_is_an_api_error(self):
        with self.assertRaises(ApiError):
            call(FakeSession(FakeResponse(bad_json=True)))

    def test_zero_retries_means_one_attempt(self):
        session = FakeSession(FakeResponse(503))
        with self.assertRaises(ApiError):
            call(session, max_retries=0)
        self.assertEqual(len(session.calls), 1)

    def test_other_request_exceptions_fail_immediately(self):
        session = FakeSession(requests.exceptions.InvalidURL("bad"))
        with self.assertRaises(ApiError):
            call(session)
        self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
