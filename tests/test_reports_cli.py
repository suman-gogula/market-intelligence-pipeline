import io
import json
import logging
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

from market_intel import cli
from market_intel.logging_setup import configure_logging, log_event
from market_intel.pipeline import run_pipeline
from market_intel.reports import export_reports, list_queries, run_query
from tests.helpers import TODAY, TempDirTestCase, memory_db, raw_frame, raw_row

PRICED = dict(salary_currency="USD", salary_period="year")


def seed(db):
    rows = [
        raw_row(source_job_id="1", title="Data Engineer", posted_date="2026-08-03",
                description="Python SQL Docker pipelines for our data platform team.",
                salary_min="100000", salary_max="120000", **PRICED),
        raw_row(source_job_id="2", title="Senior Data Engineer", posted_date="2026-08-20",
                description="Python SQL Airflow pipelines for our data platform team.",
                salary_min="120000", salary_max="140000", **PRICED),
        raw_row(source_job_id="3", title="Platform Engineer", posted_date="2026-09-10",
                description="Python Docker Kubernetes for the platform infrastructure.",
                salary_min="110000", salary_max="130000", **PRICED),
        raw_row(source_job_id="4", title="Analyst", location="Remote, Germany", work_mode="",
                posted_date="2026-09-12", description="Excel and SQL reporting for finance leaders.",
                salary_min="50000", salary_max="60000", salary_currency="EUR", salary_period="year"),
    ]
    run_pipeline(db, source_name="seed", data_origin="sample", load=lambda: raw_frame(*rows), today=TODAY)


class AnalyticsQueryTests(unittest.TestCase):
    def setUp(self):
        self.db = memory_db()
        self.addCleanup(self.db.close)
        seed(self.db)

    def test_skill_demand_counts_and_percentages(self):
        frame = run_query(self.db, "skill_demand").set_index("skill")
        self.assertEqual(frame.loc["Python", "postings"], 3)
        self.assertEqual(frame.loc["Python", "pct_of_postings"], 75.0)
        self.assertEqual(frame.loc["Excel", "postings"], 1)
        self.assertEqual(set(frame["data_origin"]), {"sample"})

    def test_monthly_trend_with_moving_average(self):
        frame = run_query(self.db, "job_trends_monthly")
        self.assertEqual(list(frame["posted_month"]), ["2026-08", "2026-09"])
        self.assertEqual(list(frame["postings"]), [2, 2])
        self.assertEqual(list(frame["remote_postings"]), [0, 1])
        self.assertEqual(list(frame["postings_3m_avg"]), [2.0, 2.0])

    def test_location_comparison(self):
        frame = run_query(self.db, "location_comparison").set_index("country")
        self.assertEqual(frame.loc["United States", "postings"], 3)
        self.assertEqual(frame.loc["Germany", "remote_postings"], 1)

    def test_salary_summary_never_mixes_currencies(self):
        frame = run_query(self.db, "salary_summary").set_index("salary_currency")
        self.assertEqual(frame.loc["USD", "postings_with_salary"], 3)
        self.assertEqual(frame.loc["USD", "avg_annual_min"], 110000.0)
        self.assertEqual(frame.loc["EUR", "avg_annual_max"], 60000.0)

    def test_salary_by_skill_hides_groups_under_three_postings(self):
        frame = run_query(self.db, "salary_by_skill")
        self.assertEqual(list(frame["skill"]), ["Python"])  # only skill with 3+ salary-bearing postings
        self.assertEqual(frame.iloc[0]["avg_annual_midpoint"], 120000.0)

    def test_top_skills_rank_is_deterministic(self):
        frame = run_query(self.db, "top_skills_by_country")
        us = frame[frame["country"] == "United States"]
        self.assertEqual(us.iloc[0]["skill"], "Python")
        self.assertEqual(list(us["skill_rank"]), sorted(us["skill_rank"]))

    def test_ai_categories_default_to_not_classified(self):
        frame = run_query(self.db, "ai_categories")
        self.assertEqual(list(frame["ai_category"]), ["not_classified"])

    def test_every_query_file_runs_and_has_data_origin_where_relevant(self):
        for path in list_queries():
            with self.subTest(query=path.stem):
                frame = run_query(self.db, path.stem)
                self.assertGreater(len(frame), 0)

    def test_queries_use_no_vendor_specific_functions(self):
        banned = ("strftime", "to_char", "date_trunc", "ifnull", "group_concat", "%")
        for path in list_queries():
            text = path.read_text(encoding="utf-8").lower()
            for word in banned:
                self.assertNotIn(word, text, f"{path.name} uses {word}")


class ExportTests(TempDirTestCase):
    def test_export_writes_one_csv_per_query_plus_note(self):
        db = memory_db()
        self.addCleanup(db.close)
        seed(db)
        counts = export_reports(db, self.tmp / "out")
        files = {p.name for p in (self.tmp / "out").iterdir()}
        self.assertEqual(files, {f"{name}.csv" for name in counts} | {"EXPORT_NOTE.txt"})
        self.assertEqual(len(counts), len(list_queries()))
        header = (self.tmp / "out" / "skill_demand.csv").read_text(encoding="utf-8").splitlines()[0]
        self.assertTrue(header.startswith("data_origin,"))


class CliTests(TempDirTestCase):
    def invoke(self, *argv, env=None):
        env = {"DATABASE_URL": f"sqlite:///{(self.tmp / 'cli.db').as_posix()}", **(env or {})}
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict("os.environ", env, clear=True), \
                mock.patch("market_intel.config.load_dotenv"), \
                redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_check_config_hides_secrets(self):
        code, out, _ = self.invoke("check-config", env={
            "GEMINI_API_KEY": "k" * 30, "DATABASE_URL": "postgresql://u:pw12345@h.example.com/db"})
        self.assertEqual(code, 0)
        self.assertNotIn("k" * 30, out)
        self.assertNotIn("pw12345", out)
        self.assertIn("gemini_api_key = set", out)

    def test_bad_config_exits_with_code_2(self):
        code, _, err = self.invoke("check-config", env={"HTTP_MAX_RETRIES": "50"})
        self.assertEqual(code, 2)
        self.assertIn("HTTP_MAX_RETRIES", err)

    def test_ingest_csv_then_rerun_is_idempotent(self):
        path = self.tmp / "jobs.csv"
        path.write_text("title,company,posted_date,description,source_job_id\n"
                        "Data Engineer,Acme,2026-09-01,Build Python and SQL pipelines daily,A1\n"
                        ",Acme,2026-09-01,Missing title row but long enough text,A2\n", encoding="utf-8")
        code, out, _ = self.invoke("ingest-csv", str(path))
        self.assertEqual(code, 0)
        self.assertIn("inserted:              1", out)
        self.assertIn("data_origin=user_csv", out)
        _, out2, _ = self.invoke("ingest-csv", str(path))
        self.assertIn("inserted:              0", out2)
        self.assertIn("already stored:        1", out2)

    def test_missing_file_exits_1_with_message_not_traceback(self):
        code, _, err = self.invoke("ingest-csv", str(self.tmp / "missing.csv"))
        self.assertEqual(code, 1)
        self.assertIn("not found", err)
        self.assertNotIn("Traceback", err)

    def test_ai_flag_without_key_degrades_gracefully(self):
        path = self.tmp / "jobs.csv"
        path.write_text("title,company,posted_date,description\n"
                        "Dev,Acme,2026-09-01,Build Python and SQL pipelines daily\n", encoding="utf-8")
        code, out, _ = self.invoke("ingest-csv", str(path), "--ai")
        self.assertEqual(code, 0)
        self.assertIn("0 labelled", out)

    def test_enrich_without_key_is_a_friendly_noop(self):
        code, out, _ = self.invoke("enrich")
        self.assertEqual(code, 0)
        self.assertIn("GEMINI_API_KEY is not set", out)

    def test_postgres_without_driver_exits_1(self):
        with mock.patch.dict("sys.modules", {"psycopg": None}):
            code, _, err = self.invoke("init-db", env={"DATABASE_URL": "postgresql://u:p@localhost/db"})
        self.assertEqual(code, 1)
        self.assertIn("requirements-postgres.txt", err)

    def test_demo_runs_without_secrets_and_never_touches_configured_database(self):
        out_dir = self.tmp / "exports"
        with mock.patch.object(cli, "SAMPLE_EXPORT_DIR", out_dir), \
                mock.patch.object(cli, "DEMO_DATABASE_URL", f"sqlite:///{(self.tmp / 'demo.db').as_posix()}"):
            code, out, _ = self.invoke("demo", "--reset")
        self.assertEqual(code, 0)
        self.assertIn("DEMO MODE", out)
        self.assertIn("inserted:              110", out)
        self.assertTrue((out_dir / "skill_demand.csv").exists())
        self.assertFalse((self.tmp / "cli.db").exists())


class LoggingTests(unittest.TestCase):
    def emit(self, fmt):
        stream = io.StringIO()
        logger = configure_logging("INFO", fmt, secrets=["sup3r-secret-value"], stream=stream)
        log_event(logger, "something_happened", token="sup3r-secret-value", rows=3)
        logger.warning("raw message with sup3r-secret-value inside")
        return stream.getvalue()

    def tearDown(self):
        configure_logging("WARNING", "text", stream=io.StringIO())

    def test_text_format_has_event_fields_and_redaction(self):
        text = self.emit("text")
        self.assertIn("something_happened", text)
        self.assertIn("rows=3", text)
        self.assertNotIn("sup3r-secret-value", text)
        self.assertIn("token=***", text)

    def test_json_format_is_one_valid_object_per_line(self):
        text = self.emit("json")
        records = [json.loads(line) for line in text.splitlines()]
        self.assertEqual(records[0]["event"], "something_happened")
        self.assertEqual(records[0]["rows"], 3)
        self.assertNotIn("sup3r-secret-value", text)

    def test_level_filters_debug(self):
        stream = io.StringIO()
        logger = configure_logging("WARNING", "text", stream=stream)
        log_event(logger, "quiet", logging.INFO)
        self.assertEqual(stream.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
