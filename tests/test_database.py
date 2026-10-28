import sqlite3
import sys
import unittest
from unittest import mock

from market_intel.database import (Database, DatabaseError, _to_psycopg, parse_database_url,
                                   redact_database_url, split_statements, to_python)
from tests.helpers import TempDirTestCase, memory_db


class UrlTests(unittest.TestCase):
    def test_sqlite_urls(self):
        self.assertEqual(parse_database_url("sqlite:///data/x.db").location, "data/x.db")
        self.assertEqual(parse_database_url("sqlite:////abs/x.db").location, "/abs/x.db")
        self.assertEqual(parse_database_url("sqlite:///C:/Users/me/x.db").location, "C:/Users/me/x.db")
        self.assertEqual(parse_database_url("sqlite:///:memory:").location, ":memory:")

    def test_bad_urls(self):
        for url in ("sqlite://", "sqlite://host/x.db", "mysql://h/db", "postgresql://", "nonsense"):
            with self.subTest(url=url), self.assertRaises(DatabaseError):
                parse_database_url(url)

    def test_postgres_url_is_accepted(self):
        self.assertEqual(parse_database_url("postgresql://u:p@h.example.com:5432/db").kind, "postgresql")

    def test_redaction(self):
        shown = redact_database_url("postgresql://bob:hunter2@h.example.com:5432/db?sslmode=require")
        self.assertNotIn("hunter2", shown)
        self.assertIn("bob", shown)
        self.assertNotIn("topsecret", redact_database_url("postgresql://h/db?password=topsecret&x=1"))
        self.assertEqual(redact_database_url("sqlite:///a.db"), "sqlite:///a.db")


class HelperTests(unittest.TestCase):
    def test_placeholder_conversion_for_postgres(self):
        sql = "SELECT * FROM t WHERE a = :a AND b LIKE 'x%' AND c = :b_2 AND ts > '12:30'"
        self.assertEqual(_to_psycopg(sql),
                         "SELECT * FROM t WHERE a = %(a)s AND b LIKE 'x%%' AND c = %(b_2)s AND ts > '12:30'")

    def test_split_statements_ignores_blank_pieces(self):
        self.assertEqual(split_statements("A;\n\nB;  ;"), ["A", "B"])

    def test_to_python_handles_missing_and_numpy_values(self):
        import numpy as np
        import pandas as pd
        self.assertIsNone(to_python(float("nan")))
        self.assertIsNone(to_python(pd.NA))
        self.assertEqual(to_python(np.int64(3)), 3)
        self.assertIsInstance(to_python(np.float64(1.5)), float)
        self.assertEqual(to_python("text"), "text")


class SqliteBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.db = memory_db()
        self.addCleanup(self.db.close)

    def test_schema_creation_is_idempotent_and_creates_all_tables(self):
        self.db.init_schema()
        self.db.init_schema()
        names = set(self.db.query("SELECT name FROM sqlite_master WHERE type = 'table'")["name"])
        self.assertTrue({"pipeline_runs", "skill_catalog", "job_postings", "job_skills",
                         "rejected_records"} <= names)

    def test_query_returns_dataframe_and_binds_parameters(self):
        self.db.init_schema()
        self.db.execute("INSERT INTO skill_catalog (skill, category) VALUES (:s, :c)",
                        {"s": "x'; DROP TABLE skill_catalog; --", "c": "test"})
        frame = self.db.query("SELECT skill FROM skill_catalog WHERE category = :c", {"c": "test"})
        self.assertEqual(list(frame["skill"]), ["x'; DROP TABLE skill_catalog; --"])
        self.assertEqual(len(self.db.query("SELECT * FROM skill_catalog")), 1)

    def test_transaction_rolls_back_on_error(self):
        self.db.init_schema()
        with self.assertRaises(RuntimeError), self.db.transaction():
            self.db.execute("INSERT INTO skill_catalog (skill, category) VALUES ('a', 'b')")
            raise RuntimeError("boom")
        self.assertEqual(len(self.db.query("SELECT * FROM skill_catalog")), 0)

    def test_constraints_reject_bad_rows(self):
        self.db.init_schema()
        with self.assertRaises(sqlite3.IntegrityError):  # unknown skill breaks the foreign key
            self.db.execute("INSERT INTO job_skills (job_id, skill) VALUES ('nope', 'nope')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO pipeline_runs (run_id, source_name, data_origin, status, "
                            "started_at) VALUES ('r', 's', 'made_up', 'running', 'now')")

    def test_use_before_connect_is_a_clear_error(self):
        with self.assertRaises(DatabaseError):
            Database("sqlite:///:memory:").query("SELECT 1")


class FileAndDriverTests(TempDirTestCase):
    def test_sqlite_file_is_created_with_parent_folders_and_persists(self):
        url = f"sqlite:///{(self.tmp / 'nested' / 'app.db').as_posix()}"
        with Database(url) as db:
            db.init_schema()
        with Database(url) as db:
            self.assertIn("job_postings", set(db.query("SELECT name FROM sqlite_master")["name"]))

    def test_missing_postgres_driver_gives_install_hint(self):
        with mock.patch.dict(sys.modules, {"psycopg": None}):
            with self.assertRaisesRegex(DatabaseError, "requirements-postgres.txt"):
                Database("postgresql://u:p@localhost/db").connect()


if __name__ == "__main__":
    unittest.main()
