import unittest
from datetime import date

from market_intel.normalize import (annualize, normalize_employment_type, normalize_key,
                                    normalize_work_mode, parse_amount, parse_iso_date,
                                    parse_location, parse_salary_text, strip_html)


class DateAndAmountTests(unittest.TestCase):
    def test_dates_accept_iso_with_optional_time(self):
        self.assertEqual(parse_iso_date("2026-03-05"), date(2026, 3, 5))
        self.assertEqual(parse_iso_date("2026-03-05T10:23:26"), date(2026, 3, 5))

    def test_dates_reject_other_formats_and_impossible_days(self):
        for bad in ("05/03/2026", "2026-3-5", "2026-13-45", "yesterday", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_iso_date(bad)

    def test_amounts(self):
        self.assertEqual(parse_amount("85,000"), 85000.0)
        self.assertEqual(parse_amount("42.5"), 42.5)
        for bad in ("-1", "abc", "1e5", ""):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                parse_amount(bad)

    def test_annualize(self):
        self.assertEqual(annualize(50, "hour"), 104000.0)
        self.assertEqual(annualize(5000, "month"), 60000.0)
        self.assertEqual(annualize(90000, "year"), 90000.0)


class SalaryTextTests(unittest.TestCase):
    def test_parses_ranges_and_single_values(self):
        self.assertEqual(parse_salary_text("$40,000 - $50,000"), (40000.0, 50000.0))
        self.assertEqual(parse_salary_text("$70k-$90k"), (70000.0, 90000.0))
        self.assertEqual(parse_salary_text("100000 USD per year"), (100000.0, 100000.0))

    def test_refuses_to_guess_when_units_or_currency_are_unclear(self):
        for text in ("", "Competitive", "$50/hour", "EUR 60000", "\u00a345,000", "$1 $2 $3"):
            with self.subTest(text=text):
                self.assertIsNone(parse_salary_text(text))


class LocationAndModeTests(unittest.TestCase):
    def test_city_region_country(self):
        self.assertEqual(parse_location("Austin, TX, US"), ("Austin", "United States"))
        self.assertEqual(parse_location("  london ,  UK "), ("London", "United Kingdom"))

    def test_remote_markers_are_dropped(self):
        self.assertEqual(parse_location("Remote, Germany"), ("Not specified", "Germany"))
        self.assertEqual(parse_location("Remote"), ("Not specified", "Unknown"))
        self.assertEqual(parse_location("Worldwide"), ("Not specified", "Unknown"))

    def test_unknown_single_word_is_a_city_and_unknown_country_is_kept(self):
        self.assertEqual(parse_location("Lisbon"), ("Lisbon", "Unknown"))
        self.assertEqual(parse_location("Nairobi, Kenya"), ("Nairobi", "Kenya"))
        self.assertEqual(parse_location(None), ("Not specified", "Unknown"))

    def test_work_mode_prefers_explicit_value_then_location(self):
        self.assertEqual(normalize_work_mode("On-Site", "Remote, US"), "onsite")
        self.assertEqual(normalize_work_mode("", "Remote, US"), "remote")
        self.assertEqual(normalize_work_mode("???", "Berlin"), "unknown")

    def test_employment_type(self):
        self.assertEqual(normalize_employment_type("Full-Time"), "full_time")
        self.assertEqual(normalize_employment_type("freelance"), "contract")
        self.assertEqual(normalize_employment_type("volunteer"), "unknown")


class TextTests(unittest.TestCase):
    def test_key_ignores_case_spacing_and_punctuation_but_keeps_c_plus_plus(self):
        self.assertEqual(normalize_key("  Senior  Data-Engineer (Remote)! "), "senior data engineer remote")
        self.assertEqual(normalize_key("C++ Developer"), "c++ developer")

    def test_strip_html_keeps_text_and_drops_scripts(self):
        html = "<p>Build <b>pipelines</b></p><ul><li>Python</li><li>SQL</li></ul><script>alert(1)</script>"
        self.assertEqual(strip_html(html), "Build pipelines Python SQL")
        self.assertEqual(strip_html("Fish &amp; chips"), "Fish & chips")


if __name__ == "__main__":
    unittest.main()
