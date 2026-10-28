import unittest

from market_intel.config import load_settings
from market_intel.http_client import ApiError
from market_intel.sources import RAW_COLUMNS, SourceError, fetch_remotive, load_csv
from tests.helpers import TempDirTestCase

HEADER = "title,company,posted_date,description\n"
GOOD_LINE = "Data Engineer,Acme,2026-09-01,Build pipelines with Python and SQL every day\n"


class LoadCsvTests(TempDirTestCase):
    def write(self, text, name="jobs.csv", encoding="utf-8"):
        path = self.tmp / name
        path.write_bytes(text.encode(encoding))
        return path

    def test_loads_text_columns_and_fills_optional_ones(self):
        frame = load_csv(self.write(HEADER + GOOD_LINE))
        self.assertEqual(list(frame.columns), RAW_COLUMNS)
        self.assertEqual(frame.iloc[0]["title"], "Data Engineer")
        self.assertEqual(frame.iloc[0]["salary_min"], "")

    def test_blank_cells_stay_empty_strings_not_nan(self):
        frame = load_csv(self.write(HEADER + "Analyst,,2026-09-01,desc\n"))
        self.assertEqual(frame.iloc[0]["company"], "")

    def test_handles_utf8_bom_header_case_and_unknown_columns(self):
        text = "\ufeffTitle,COMPANY,posted_date,description,favourite_colour\nX,Y,2026-09-01,Z,blue\n"
        frame = load_csv(self.write(text))
        self.assertEqual(frame.iloc[0]["company"], "Y")
        self.assertNotIn("favourite_colour", frame.columns)

    def test_missing_file(self):
        with self.assertRaisesRegex(SourceError, "not found"):
            load_csv(self.tmp / "nope.csv")

    def test_empty_file_and_header_only_file(self):
        with self.assertRaisesRegex(SourceError, "empty"):
            load_csv(self.write(""))
        self.assertEqual(len(load_csv(self.write(HEADER, name="header_only.csv"))), 0)

    def test_missing_required_column(self):
        with self.assertRaisesRegex(SourceError, "company"):
            load_csv(self.write("title,posted_date,description\nA,2026-09-01,B\n"))

    def test_structurally_broken_csv_fails_the_file_with_a_clear_message(self):
        with self.assertRaisesRegex(SourceError, "malformed"):
            load_csv(self.write(HEADER + GOOD_LINE + "a,b,c,d,e,f,g\n"))

    def test_non_utf8_bytes_are_reported(self):
        with self.assertRaisesRegex(SourceError, "UTF-8"):
            load_csv(self.write(HEADER + "Caf\xe9 dev,Acme,2026-09-01,desc here\n", encoding="latin-1"))


REMOTIVE_PAYLOAD = {"job-count": 3, "jobs": [
    {"id": 11, "url": "https://remotive.com/remote-jobs/x-11", "title": "Python Developer",
     "company_name": "Remote Co", "job_type": "full_time", "publication_date": "2026-10-01T10:23:26",
     "candidate_required_location": "Worldwide", "salary": "$40,000 - $50,000",
     "description": "<p>Use <b>Python</b> &amp; SQL</p>"},
    {"id": 12, "title": "Writer", "company_name": "Words Inc", "publication_date": "2026-10-02T08:00:00",
     "candidate_required_location": "USA", "salary": "Competitive", "description": "<div>Write</div>"},
    "not-an-object",
]}


class FetchRemotiveTests(unittest.TestCase):
    settings = load_settings({})

    def fetch(self, payload=None, error=None, **kwargs):
        seen = {}

        def fake_request(method, url, **kw):
            seen.update(method=method, url=url, **kw)
            if error:
                raise error
            return payload

        frame = fetch_remotive(self.settings, request=fake_request, **kwargs) if not error else None
        return frame, seen

    def test_maps_fields_strips_html_and_parses_salary(self):
        frame, seen = self.fetch(REMOTIVE_PAYLOAD, category="software-dev")
        self.assertEqual(len(frame), 2)  # the non-object entry is skipped
        first = frame.iloc[0]
        self.assertEqual((first["source_job_id"], first["company"], first["work_mode"]),
                         ("11", "Remote Co", "remote"))
        self.assertEqual(first["description"], "Use Python & SQL")
        self.assertEqual((first["salary_min"], first["salary_max"], first["salary_currency"],
                          first["salary_period"]), ("40000", "50000", "USD", "year"))
        self.assertEqual(first["source_url"], "https://remotive.com/remote-jobs/x-11")
        second = frame.iloc[1]
        self.assertEqual((second["salary_min"], second["salary_currency"]), ("", ""))
        self.assertEqual(seen["params"], {"limit": 50, "category": "software-dev"})
        self.assertEqual(seen["timeout"], 10.0)

    def test_limit_override(self):
        _, seen = self.fetch({"jobs": []}, limit=5)
        self.assertEqual(seen["params"]["limit"], 5)

    def test_empty_job_list_gives_empty_frame(self):
        frame, _ = self.fetch({"jobs": []})
        self.assertEqual((len(frame), list(frame.columns)), (0, RAW_COLUMNS))

    def test_unexpected_shapes_are_source_errors(self):
        for payload in ([], {"jobs": "nope"}, {"other": 1}, None):
            with self.subTest(payload=payload), self.assertRaises(SourceError):
                self.fetch(payload)

    def test_api_failure_propagates(self):
        with self.assertRaises(ApiError):
            fetch_remotive(self.settings, request=lambda *a, **k: (_ for _ in ()).throw(ApiError("down")))


if __name__ == "__main__":
    unittest.main()
