"""Technical-skill catalogue and extraction from job text.

Matching is dictionary-based on purpose: it is deterministic, explainable and
needs no model. Aliases are matched on token boundaries so "Java" does not
fire inside "JavaScript" and "SQL" does not fire inside "NoSQL". Ambiguous
English words (Excel, Spark, React) only match with their capitalisation.
Single-letter names (R, C) are left out, and "Go" is only found as "Golang",
because plain text cannot separate them from ordinary words.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Skill:
    name: str
    category: str
    aliases: tuple[str, ...] = ()
    case_sensitive: bool = False
    match_name: bool = True  # False when the canonical name is too ambiguous to search for


CATALOG: tuple[Skill, ...] = (
    Skill("Python", "programming_language", ("python3",)),
    Skill("SQL", "programming_language", ("t-sql", "pl/sql")),
    Skill("Java", "programming_language"),
    Skill("JavaScript", "programming_language"),
    Skill("TypeScript", "programming_language"),
    Skill("C++", "programming_language"),
    Skill("C#", "programming_language"),
    Skill(".NET", "programming_language", ("asp.net", "dotnet")),
    Skill("Scala", "programming_language"),
    Skill("Rust", "programming_language"),
    Skill("Go", "programming_language", ("golang",), match_name=False),
    Skill("PostgreSQL", "database", ("postgres",)),
    Skill("MySQL", "database"),
    Skill("SQL Server", "database", ("mssql", "microsoft sql server")),
    Skill("MongoDB", "database", ("mongo db",)),
    Skill("Redis", "database"),
    Skill("Elasticsearch", "database", ("opensearch",)),
    Skill("Snowflake", "database"),
    Skill("BigQuery", "database", ("google bigquery",)),
    Skill("Redshift", "database", ("amazon redshift",)),
    Skill("Databricks", "data_processing"),
    Skill("Spark", "data_processing", ("Apache Spark", "PySpark"), case_sensitive=True),
    Skill("Hadoop", "data_processing"),
    Skill("Kafka", "data_processing", ("apache kafka",)),
    Skill("Airflow", "data_processing", ("apache airflow",)),
    Skill("dbt", "data_processing", ("data build tool",)),
    Skill("pandas", "data_processing"),
    Skill("NumPy", "data_processing"),
    Skill("ETL", "data_processing"),
    Skill("AWS", "cloud_devops", ("amazon web services",)),
    Skill("Azure", "cloud_devops", ("microsoft azure",)),
    Skill("GCP", "cloud_devops", ("google cloud", "google cloud platform")),
    Skill("Docker", "cloud_devops"),
    Skill("Kubernetes", "cloud_devops", ("k8s",)),
    Skill("Terraform", "cloud_devops"),
    Skill("Linux", "cloud_devops"),
    Skill("Git", "cloud_devops"),
    Skill("CI/CD", "cloud_devops", ("cicd", "continuous integration")),
    Skill("Power BI", "analytics_bi", ("powerbi",)),
    Skill("Tableau", "analytics_bi"),
    Skill("Looker", "analytics_bi"),
    Skill("Excel", "analytics_bi", ("Microsoft Excel",), case_sensitive=True),
    Skill("Machine Learning", "machine_learning", ("ml engineering",)),
    Skill("scikit-learn", "machine_learning", ("sklearn",)),
    Skill("TensorFlow", "machine_learning"),
    Skill("PyTorch", "machine_learning"),
    Skill("NLP", "machine_learning", ("natural language processing",)),
    Skill("Django", "framework"),
    Skill("Flask", "framework"),
    Skill("FastAPI", "framework"),
    Skill("React", "framework", ("React.js", "ReactJS"), case_sensitive=True),
    Skill("Node.js", "framework", ("nodejs",)),
    Skill("Spring Boot", "framework"),
    Skill("REST API", "framework", ("rest apis", "restful", "restful api", "restful apis")),
)


def _compile(skill: Skill) -> re.Pattern:
    names = set(skill.aliases) | ({skill.name} if skill.match_name else set())
    # Longest first so "Apache Spark" wins over "Spark" inside one alternation.
    alternation = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    pattern = rf"(?<![A-Za-z0-9+#])(?:{alternation})(?![A-Za-z0-9+#])"
    return re.compile(pattern, 0 if skill.case_sensitive else re.IGNORECASE)


_PATTERNS = tuple((skill.name, _compile(skill)) for skill in CATALOG)


def extract_skills(text: str) -> list[str]:
    """Return the canonical names of catalogue skills mentioned in ``text`` (sorted, unique)."""
    return sorted(name for name, pattern in _PATTERNS if pattern.search(text or ""))
