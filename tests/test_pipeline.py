import unittest
from unittest import mock

import pandas as pd

from market_intel.database import Database
from market_intel.paths import SAMPLE_CSV
from market_intel.pipeline import PipelineError, run_pipeline
from market_intel.sources import SourceError, load_csv
from tests.helpers import TODAY, memory_db, raw_frame, raw_row


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.db = memory_db()
        self.addCleanup(self.db.close)

    def run_with(self, *rows, origin="user_csv", name="test.csv", **kwargs):
        return run_pipeline(self.db, source_name=name, data_origin=origin,
                            load=lambda: raw_frame(*rows), today=TODAY, **kwargs)

    def count(self, table):
        return int(self.db.query(f"SELECT COUNT(*) AS n FROM {table}")["n"][0])

    def test_normal_run_stores_jobs_skills_and_audit_row(self):
        summary = self.run_with(raw_row(), raw_row(source_job_id="T-2", title="Analyst"))
        self.assertEqual((summary.rows_read, summary.rows_inserted, summary.rows_rejected), (2, 2, 0))
        self.assertEqual(self.count("job_postings"), 2)
        self.assertGreaterEqual(self.count("job_skills"), 3)
        run = self.db.query("SELECT * FROM pipeline_runs").iloc[0]
        self.assertEqual((run["status"], run["rows_inserted"], run["data_origin"]),
                         ("succeeded", 2, "user_csv"))

    def test_rerunning_the_same_input_inserts_nothing_new(self):
        self.run_with(raw_row())
        second = self.run_with(raw_row())
        self.assertEqual((second.rows_inserted, second.rows_already_stored), (0, 1))
        self.assertEqual((self.count("job_postings"), self.count("pipeline_runs")), (1, 2))

    def test_overlapping_input_only_adds_new_rows(self):
        self.run_with(raw_row())
        second = self.run_with(raw_row(), raw_row(source_job_id="T-9", title="ML Engineer"))
        self.assertEqual((second.rows_inserted, second.rows_already_stored), (1, 1))
        self.assertEqual(self.count("job_skills"), len(self.db.query("SELECT DISTINCT job_id, skill FROM job_skills")))

    def test_same_listing_from_a_second_source_is_not_stored_twice(self):
        self.run_with(raw_row(), name="source_a")
        second = self.run_with(raw_row(source_job_id="other-id"), name="source_b")
        self.assertEqual((second.rows_inserted, second.rows_already_stored), (0, 1))

    def test_bad_rows_are_rejected_and_recorded_but_good_rows_load(self):
        summary = self.run_with(raw_row(), raw_row(source_job_id="B", title=""),
                                raw_row(source_job_id="C", posted_date="garbage"))
        self.assertEqual((summary.rows_inserted, summary.rows_rejected), (1, 2))
        rejected = self.db.query("SELECT row_number, reason FROM rejected_records ORDER BY row_number")
        self.assertEqual(list(rejected["row_number"]), [2, 3])
        self.assertIn("missing title", rejected.iloc[0]["reason"])

    def test_duplicates_inside_one_file_are_counted(self):
        summary = self.run_with(raw_row(), raw_row())
        self.assertEqual((summary.rows_duplicate_in_batch, summary.rows_inserted), (1, 1))

    def test_all_rows_invalid_still_succeeds(self):
        summary = self.run_with(raw_row(title=""))
        self.assertEqual((summary.rows_inserted, summary.rows_rejected), (0, 1))
        self.assertEqual(self.db.query("SELECT status FROM pipeline_runs")["status"][0], "succeeded")

    def test_origins_are_stored_separately(self):
        self.run_with(raw_row(), origin="sample")
        self.run_with(raw_row(source_job_id="L1", title="Other Role"), origin="live")
        counts = self.db.query("SELECT data_origin, COUNT(*) AS n FROM job_postings GROUP BY data_origin")
        self.assertEqual(dict(zip(counts["data_origin"], counts["n"])), {"sample": 1, "live": 1})

    def test_unknown_origin_is_refused_before_touching_the_database(self):
        with self.assertRaises(ValueError):
            self.run_with(raw_row(), origin="made_up")

    def test_source_failure_is_recorded_as_failed_run_and_raised(self):
        def broken():
            raise SourceError("API unavailable")
        with self.assertRaisesRegex(PipelineError, "API unavailable") as caught:
            run_pipeline(self.db, source_name="x", data_origin="live", load=broken)
        run = self.db.query("SELECT status, error_message FROM pipeline_runs").iloc[0]
        self.assertEqual(run["status"], "failed")
        self.assertIn("API unavailable", run["error_message"])
        self.assertTrue(caught.exception.run_id)

    def test_database_error_midway_rolls_back_every_row_of_that_run(self):
        original = Database.execute
        inserts = {"n": 0}

        def flaky(self_db, sql, params=None):
            if sql.lstrip().startswith("INSERT INTO job_postings"):
                inserts["n"] += 1
                if inserts["n"] == 2:
                    raise RuntimeError("disk full")
            return original(self_db, sql, params)

        with mock.patch.object(Database, "execute", flaky):
            with self.assertRaises(PipelineError):
                self.run_with(raw_row(), raw_row(source_job_id="T-2", title="Analyst"))
        self.assertEqual((self.count("job_postings"), self.count("job_skills")), (0, 0))
        self.assertEqual(self.db.query("SELECT status FROM pipeline_runs")["status"][0], "failed")
        retry = self.run_with(raw_row(), raw_row(source_job_id="T-2", title="Analyst"))
        self.assertEqual(retry.rows_inserted, 2)

    def test_missing_csv_file_is_a_recorded_failure(self):
        with self.assertRaises(PipelineError):
            run_pipeline(self.db, source_name="gone", data_origin="user_csv",
                         load=lambda: load_csv("/definitely/not/here.csv"))
        self.assertEqual(self.db.query("SELECT status FROM pipeline_runs")["status"][0], "failed")


class SampleDatasetTests(unittest.TestCase):
    def test_bundled_sample_loads_with_expected_shape(self):
        db = memory_db()
        self.addCleanup(db.close)
        summary = run_pipeline(db, source_name="sample_jobs.csv", data_origin="sample",
                               load=lambda: load_csv(SAMPLE_CSV), today=TODAY)
        self.assertEqual(summary.rows_read, 129)
        self.assertEqual((summary.rows_rejected, summary.rows_duplicate_in_batch), (10, 9))
        self.assertEqual(summary.rows_inserted, 110)
        again = run_pipeline(db, source_name="sample_jobs.csv", data_origin="sample",
                             load=lambda: load_csv(SAMPLE_CSV), today=TODAY)
        self.assertEqual((again.rows_inserted, again.rows_already_stored), (0, 110))
        self.assertTrue(set(pd.read_csv(SAMPLE_CSV)["source_job_id"].str[:4]) == {"SYN-"})


if __name__ == "__main__":
    unittest.main()
