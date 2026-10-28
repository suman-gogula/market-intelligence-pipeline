import json
import unittest

from market_intel.config import load_settings
from market_intel.enrich import MAX_CONSECUTIVE_FAILURES, enrich_pending
from market_intel.gemini import CATEGORIES, AiError, Classification, GeminiClassifier
from market_intel.http_client import ApiError
from market_intel.pipeline import run_pipeline
from tests.helpers import TODAY, memory_db, raw_frame, raw_row


def gemini_reply(text):
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


def make_classifier(request, **kwargs):
    defaults = dict(timeout=5, max_retries=1, min_interval_seconds=0, request=request, sleep=lambda s: None)
    return GeminiClassifier("k" * 30, "test-model", **{**defaults, **kwargs})


class GeminiClassifierTests(unittest.TestCase):
    def test_success_returns_validated_classification_and_sends_key_as_header(self):
        seen = {}

        def request(method, url, **kwargs):
            seen.update(url=url, **kwargs)
            return gemini_reply(json.dumps({"category": "data_engineering", "summary": "Builds  pipelines."}))

        result = make_classifier(request).classify("Data Engineer", "Python")
        self.assertEqual(result, Classification("data_engineering", "Builds pipelines."))
        self.assertEqual(seen["headers"], {"x-goog-api-key": "k" * 30})
        self.assertNotIn("k" * 30, seen["url"])
        self.assertIn("test-model:generateContent", seen["url"])

    def test_bad_replies_become_ai_errors(self):
        replies = [
            {}, {"candidates": []}, gemini_reply("not json"), gemini_reply("[1]"),
            gemini_reply(json.dumps({"category": "astrology", "summary": "x"})),
            gemini_reply(json.dumps({"category": "other", "summary": "  "})),
            gemini_reply(json.dumps({"category": "other"})),
        ]
        for reply in replies:
            with self.subTest(reply=str(reply)[:50]), self.assertRaises(AiError):
                make_classifier(lambda *a, **k: reply).classify("t", "d")

    def test_http_failure_becomes_ai_error(self):
        def request(*a, **k):
            raise ApiError("HTTP 429")
        with self.assertRaises(AiError):
            make_classifier(request).classify("t", "d")

    def test_summary_is_length_limited_and_prompt_is_truncated(self):
        bodies = []

        def request(method, url, **kwargs):
            bodies.append(kwargs["json_body"])
            return gemini_reply(json.dumps({"category": "other", "summary": "w " * 500}))

        result = make_classifier(request).classify("t", "x" * 50_000)
        self.assertLessEqual(len(result.summary), 300)
        self.assertLess(len(json.dumps(bodies[0])), 6000)

    def test_calls_are_spaced_by_min_interval(self):
        clock = {"now": 100.0}
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            clock["now"] += seconds

        request = lambda *a, **k: gemini_reply(json.dumps({"category": "other", "summary": "ok"}))
        classifier = make_classifier(request, min_interval_seconds=6, sleep=sleep, clock=lambda: clock["now"])
        classifier.classify("a", "b")
        classifier.classify("a", "b")
        self.assertEqual(sleeps, [6])

    def test_from_settings(self):
        settings = load_settings({"GEMINI_API_KEY": "k" * 30, "GEMINI_MODEL": "m-1"})
        self.assertEqual(GeminiClassifier.from_settings(settings).model, "m-1")

    def test_category_list_contains_fallback(self):
        self.assertIn("other", CATEGORIES)


class FakeClassifier:
    model = "fake-model"

    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def classify(self, title, description):
        self.calls += 1
        outcome = self.outcomes.pop(0) if self.outcomes else Classification("other", "fallback")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class EnrichmentTests(unittest.TestCase):
    def setUp(self):
        self.db = memory_db()
        self.addCleanup(self.db.close)

    def load(self, count, origin="user_csv", **kwargs):
        rows = [raw_row(source_job_id=f"J{i}", title=f"Engineer {i}") for i in range(count)]
        return run_pipeline(self.db, source_name="t", data_origin=origin, load=lambda: raw_frame(*rows),
                            today=TODAY, **kwargs)

    def labelled(self):
        return int(self.db.query("SELECT COUNT(*) AS n FROM job_postings WHERE ai_category IS NOT NULL")["n"][0])

    def test_labels_are_stored_and_limit_is_respected(self):
        self.load(5)
        result = enrich_pending(self.db, FakeClassifier([]), max_jobs=3)
        self.assertEqual((result.enriched, self.labelled()), (3, 3))
        row = self.db.query("SELECT ai_model, ai_summary FROM job_postings WHERE ai_category IS NOT NULL").iloc[0]
        self.assertEqual((row["ai_model"], row["ai_summary"]), ("fake-model", "fallback"))
        enrich_pending(self.db, FakeClassifier([]), max_jobs=10)
        self.assertEqual(self.labelled(), 5)  # picks up only the remaining rows

    def test_single_failures_are_skipped_not_fatal(self):
        self.load(3)
        classifier = FakeClassifier([AiError("blip")])
        result = enrich_pending(self.db, classifier, max_jobs=10)
        self.assertEqual((result.enriched, result.failed, result.stopped_early), (2, 1, False))

    def test_circuit_breaker_stops_after_consecutive_failures(self):
        self.load(10)
        classifier = FakeClassifier([AiError("quota")] * 10)
        result = enrich_pending(self.db, classifier, max_jobs=10)
        self.assertEqual((classifier.calls, result.stopped_early), (MAX_CONSECUTIVE_FAILURES, True))
        self.assertEqual(self.labelled(), 0)

    def test_live_rows_are_excluded_unless_requested(self):
        self.load(2, origin="live")
        self.assertEqual(enrich_pending(self.db, FakeClassifier([]), 10).enriched, 0)
        self.assertEqual(enrich_pending(self.db, FakeClassifier([]), 10, ("live",)).enriched, 2)

    def test_zero_limit_does_nothing(self):
        self.load(1)
        classifier = FakeClassifier([])
        enrich_pending(self.db, classifier, max_jobs=0)
        self.assertEqual(classifier.calls, 0)

    def test_pipeline_succeeds_and_keeps_data_when_ai_always_fails(self):
        summary = self.load(3, classifier=FakeClassifier([AiError("down")] * 5), ai_max_jobs=5)
        self.assertEqual((summary.rows_inserted, summary.ai_enriched, summary.ai_failed), (3, 0, 3))
        self.assertEqual(self.db.query("SELECT status FROM pipeline_runs")["status"][0], "succeeded")

    def test_unexpected_ai_crash_does_not_fail_the_run(self):
        summary = self.load(2, classifier=FakeClassifier([RuntimeError("bug")]), ai_max_jobs=5)
        self.assertEqual(summary.rows_inserted, 2)
        self.assertEqual(self.db.query("SELECT status FROM pipeline_runs")["status"][0], "succeeded")

    def test_pipeline_records_ai_count(self):
        self.load(2, classifier=FakeClassifier([]), ai_max_jobs=5)
        self.assertEqual(int(self.db.query("SELECT ai_enriched FROM pipeline_runs")["ai_enriched"][0]), 2)


if __name__ == "__main__":
    unittest.main()
