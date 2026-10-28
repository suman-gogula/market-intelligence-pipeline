import unittest

import pandas as pd

from market_intel.clean import JOB_COLUMNS, clean_jobs
from market_intel.validate import validate_rows
from tests.helpers import TODAY, raw_frame, raw_row


class ValidateTests(unittest.TestCase):
    def reasons(self, **overrides) -> str:
        result = validate_rows(raw_frame(raw_row(**overrides)), TODAY)
        self.assertEqual(len(result.rejected), 1, "row should have been rejected")
        return result.rejected.iloc[0]["reason"]

    def test_good_row_passes_and_keeps_row_number(self):
        result = validate_rows(raw_frame(raw_row(), raw_row(source_job_id="T-2")), TODAY)
        self.assertEqual(len(result.valid), 2)
        self.assertEqual(list(result.valid["row_number"]), [1, 2])
        self.assertTrue(result.rejected.empty)

    def test_missing_required_fields(self):
        for field in ("title", "company", "description", "posted_date"):
            with self.subTest(field=field):
                self.assertIn(f"missing {field}", self.reasons(**{field: "   "}))

    def test_date_problems(self):
        self.assertIn("not a valid", self.reasons(posted_date="31/12/2026"))
        self.assertIn("future", self.reasons(posted_date="2026-11-30"))

    def test_short_description(self):
        self.assertIn("too short", self.reasons(description="Hiring now."))

    def test_salary_problems(self):
        base = dict(salary_currency="USD", salary_period="year")
        self.assertIn("both be present", self.reasons(salary_min="50000"))
        self.assertIn("invalid salary_min", self.reasons(salary_min="-5", salary_max="9", **base))
        self.assertIn("greater than", self.reasons(salary_min="90000", salary_max="80000", **base))
        self.assertIn("currency", self.reasons(salary_min="1", salary_max="2",
                                               salary_currency="", salary_period="year"))
        self.assertIn("salary_period", self.reasons(salary_min="80000", salary_max="90000",
                                                   salary_currency="USD", salary_period=""))
        self.assertIn("plausible", self.reasons(salary_min="5", salary_max="9", **base))

    def test_every_problem_in_a_row_is_reported(self):
        reason = self.reasons(title="", company="", posted_date="nope")
        for fragment in ("missing title", "missing company", "not a valid"):
            self.assertIn(fragment, reason)

    def test_rejected_record_keeps_shortened_original_as_json(self):
        result = validate_rows(raw_frame(raw_row(title="", description="x" * 900)), TODAY)
        record = result.rejected.iloc[0]["raw_record"]
        self.assertLess(len(record), 700)
        self.assertIn('"title": ""', record)

    def test_empty_frame_is_fine(self):
        result = validate_rows(raw_frame(), TODAY)
        self.assertTrue(result.valid.empty and result.rejected.empty)


class CleanTests(unittest.TestCase):
    def clean(self, *rows):
        valid = validate_rows(raw_frame(*rows), TODAY).valid
        return clean_jobs(valid, source_name="test.csv", data_origin="user_csv")

    def test_normalises_fields_and_annualises_salary(self):
        result = self.clean(raw_row(title="  Senior   Data Engineer ", location="remote, uk",
                                    work_mode="", salary_min="40", salary_max="50",
                                    salary_currency="gbp", salary_period="hour"))
        job = result.jobs.iloc[0]
        self.assertEqual(list(result.jobs.columns), JOB_COLUMNS)
        self.assertEqual(job["title"], "Senior Data Engineer")
        self.assertEqual(job["title_normalized"], "senior data engineer")
        self.assertEqual((job["city"], job["country"], job["work_mode"]),
                         ("Not specified", "United Kingdom", "remote"))
        self.assertEqual((job["salary_currency"], job["salary_annual_min"], job["salary_annual_max"]),
                         ("GBP", 83200.0, 104000.0))

    def test_missing_salary_stays_null(self):
        job = self.clean(raw_row()).jobs.iloc[0]
        self.assertTrue(pd.isna(job["salary_annual_min"]) and pd.isna(job["salary_currency"]))

    def test_same_source_id_is_a_duplicate(self):
        result = self.clean(raw_row(), raw_row(title="Different title", company="Other"))
        self.assertEqual((len(result.jobs), result.duplicates_in_batch), (1, 1))

    def test_same_listing_with_different_id_case_and_spacing_is_a_duplicate(self):
        result = self.clean(raw_row(source_job_id="A"),
                            raw_row(source_job_id="B", title=" DATA  engineer", company="test company"))
        self.assertEqual((len(result.jobs), result.duplicates_in_batch), (1, 1))

    def test_different_date_or_city_is_not_a_duplicate(self):
        result = self.clean(raw_row(source_job_id="A"),
                            raw_row(source_job_id="B", posted_date="2026-09-02"),
                            raw_row(source_job_id="C", location="Berlin, Germany"))
        self.assertEqual(len(result.jobs), 3)

    def test_skills_are_extracted_per_job(self):
        result = self.clean(raw_row())
        self.assertEqual(sorted(result.skills["skill"]), ["Docker", "Python", "SQL"])

    def test_no_rows_gives_empty_frames_with_columns(self):
        result = self.clean()
        self.assertEqual(list(result.jobs.columns), JOB_COLUMNS)
        self.assertTrue(result.skills.empty)


if __name__ == "__main__":
    unittest.main()
