import unittest

from market_intel.skills import CATALOG, extract_skills


class ExtractSkillsTests(unittest.TestCase):
    def test_finds_common_skills_case_insensitively(self):
        found = extract_skills("Strong PYTHON, sql and Docker required. Nice: dbt, power bi.")
        self.assertEqual(found, ["Docker", "Power BI", "Python", "SQL", "dbt"])

    def test_java_does_not_match_javascript_and_sql_does_not_match_nosql_or_postgresql(self):
        self.assertEqual(extract_skills("JavaScript and TypeScript"), ["JavaScript", "TypeScript"])
        self.assertEqual(extract_skills("NoSQL stores"), [])
        self.assertEqual(extract_skills("PostgreSQL"), ["PostgreSQL"])
        self.assertEqual(extract_skills("Java, JavaScript"), ["Java", "JavaScript"])

    def test_symbols_in_skill_names(self):
        self.assertEqual(extract_skills("C++, C# and .NET services; also Node.js, CI/CD."),
                         [".NET", "C#", "C++", "CI/CD", "Node.js"])
        self.assertEqual(extract_skills("ASP.NET shop"), [".NET"])

    def test_ambiguous_words_do_not_trigger(self):
        text = "Go-getters who excel at R&D, spark ideas and react quickly. Reading is fun."
        self.assertEqual(extract_skills(text), [])

    def test_ambiguous_names_match_with_proper_capitalisation_or_alias(self):
        self.assertEqual(extract_skills("Experience with Excel, Spark and React."), ["Excel", "React", "Spark"])
        self.assertEqual(extract_skills("We write Golang and PySpark jobs"), ["Go", "Spark"])

    def test_aliases_map_to_one_canonical_name(self):
        self.assertEqual(extract_skills("Postgres, k8s, Amazon Web Services, sklearn"),
                         ["AWS", "Kubernetes", "PostgreSQL", "scikit-learn"])

    def test_empty_input_and_uniqueness(self):
        self.assertEqual(extract_skills(""), [])
        self.assertEqual(extract_skills("SQL sql SQL"), ["SQL"])

    def test_catalogue_names_are_unique(self):
        names = [skill.name for skill in CATALOG]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
