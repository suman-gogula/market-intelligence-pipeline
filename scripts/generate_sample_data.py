"""Regenerate data/sample/sample_jobs.csv.

Everything here is invented: company names are fictional, descriptions are
assembled from templates, and the seed makes the output reproducible. A few
defective and duplicated rows are added on purpose so the validation and
duplicate-detection steps have something to demonstrate.

    python scripts/generate_sample_data.py
"""
from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

OUTPUT = Path(__file__).resolve().parents[1] / "data" / "sample" / "sample_jobs.csv"
COLUMNS = ["source_job_id", "title", "company", "location", "work_mode", "employment_type",
           "posted_date", "salary_min", "salary_max", "salary_currency", "salary_period", "description"]

COMPANIES = ["Northwind Analytics", "Fabrikam Logistics", "Contoso Retail Group", "Tailspin Health Data",
             "Wingtip Energy", "Adventure Works Mobility", "Litware Finance", "Proseware Media",
             "Lucerne Publishing Tech", "Alpine Ski Cloud", "Blue Yonder Foods", "Coho Winery Systems",
             "Trey Research Labs", "Margie's Travel Tech", "Woodgrove Payments", "Humongous Insurance Co"]

# role title -> (team, skills commonly named in the posting, in several spellings)
ROLES = {
    "Data Engineer": ("data platform", ["Python", "SQL", "Airflow", "Apache Spark", "AWS", "Docker",
                                        "Postgres", "Kafka", "dbt", "Snowflake", "Git", "ETL", "Terraform"]),
    "Analytics Engineer": ("analytics", ["SQL", "dbt", "Snowflake", "Python", "Git", "Looker",
                                         "BigQuery", "Airflow", "ETL"]),
    "Data Analyst": ("business intelligence", ["SQL", "Excel", "Power BI", "Tableau", "Python",
                                               "pandas", "Looker", "PostgreSQL"]),
    "BI Developer": ("reporting", ["Power BI", "SQL", "Excel", "SQL Server", "Tableau", "ETL", "Azure"]),
    "Data Scientist": ("data science", ["Python", "pandas", "scikit-learn", "SQL", "machine learning",
                                        "NumPy", "PyTorch", "Spark", "Git"]),
    "Machine Learning Engineer": ("machine learning", ["Python", "PyTorch", "TensorFlow", "Docker",
                                                       "Kubernetes", "AWS", "machine learning", "NLP", "CI/CD"]),
    "Backend Engineer": ("platform", ["Python", "Java", "PostgreSQL", "Redis", "Docker", "Kubernetes",
                                      "REST APIs", "FastAPI", "Django", "Git", "CI/CD"]),
    "Full Stack Developer": ("product engineering", ["JavaScript", "TypeScript", "React", "Node.js",
                                                     "PostgreSQL", "Docker", "Git", "REST APIs"]),
    "DevOps Engineer": ("infrastructure", ["Terraform", "Kubernetes", "Docker", "AWS", "Linux",
                                           "CI/CD", "Python", "Azure", "Git"]),
    "Cloud Engineer": ("cloud", ["AWS", "Azure", "GCP", "Terraform", "Kubernetes", "Linux", "Python"]),
    "Software Engineer": ("engineering", ["Java", "Spring Boot", "C#", ".NET", "SQL Server", "C++",
                                          "Git", "REST APIs", "Docker"]),
}
SENIORITY = [("", 1.0), ("Junior ", 0.7), ("Senior ", 1.3), ("Lead ", 1.55)]
DUTIES = ["design and maintain reliable production systems", "turn messy source data into trusted datasets",
          "partner with product managers to answer open business questions",
          "own features from design review through monitoring", "improve the speed and cost of existing workloads"]
EXTRAS = ["Exposure to R&D teams is a plus.", "We want go-getters who enjoy ownership.",
          "Strong written communication is expected.", "You will join a friendly, remote-aware team.",
          "Experience with NoSQL stores and JavaScript tooling is a bonus."]

# location text, country currency, base salary (yearly), work-mode weights
LOCATIONS = [
    ("Austin, TX, United States", "USD", 105_000), ("New York, NY, US", "USD", 125_000),
    ("Seattle, WA, United States", "USD", 120_000), ("London, United Kingdom", "GBP", 62_000),
    ("Manchester, UK", "GBP", 52_000), ("Berlin, Germany", "EUR", 66_000), ("Munich, Germany", "EUR", 70_000),
    ("Toronto, ON, Canada", "CAD", 95_000), ("Amsterdam, Netherlands", "EUR", 68_000),
    ("Remote, United States", "USD", 115_000), ("Remote, Germany", "EUR", 64_000),
    ("Remote, United Kingdom", "GBP", 58_000),
]


def make_job(rng: random.Random, number: int) -> dict:
    prefix, multiplier = rng.choices(SENIORITY, weights=[4, 3, 4, 1])[0]
    role = rng.choice(list(ROLES))
    team, pool = ROLES[role]
    required = rng.sample(pool, k=min(len(pool), rng.randint(3, 5)))
    nice = rng.sample([s for s in pool if s not in required] or pool, k=2)
    location, currency, base = rng.choice(LOCATIONS)
    work_mode = "remote" if location.startswith("Remote") else rng.choice(["hybrid", "onsite", "onsite"])
    company = rng.choice(COMPANIES)
    title = f"{prefix}{role}"
    # Later months get more postings so the trend chart has a visible shape.
    posted = date(2026, 1, 5) + timedelta(days=int(rng.triangular(0, 283, 230)))
    description = (f"{company} is hiring a {title} for its {team} team. You will {rng.choice(DUTIES)}. "
                   f"Required experience: {', '.join(required)}. Nice to have: {', '.join(nice)}. "
                   f"{rng.choice(EXTRAS)}")
    employment = rng.choices(["full_time", "contract", "part_time"], weights=[8, 2, 1])[0]
    row = {"source_job_id": f"SYN-{number:04d}", "title": title, "company": company,
           "location": location, "work_mode": work_mode, "employment_type": employment,
           "posted_date": posted.isoformat(), "salary_min": "", "salary_max": "",
           "salary_currency": "", "salary_period": "", "description": description}
    if rng.random() < 0.6:
        yearly = base * multiplier * rng.uniform(0.9, 1.1)
        spread = rng.uniform(0.10, 0.22)
        if employment == "contract":
            low, high, period = (round(yearly * (1 - spread) / 2080 / 5) * 5,
                                 round(yearly * (1 + spread) / 2080 / 5) * 5, "hour")
        else:
            low, high, period = (round(yearly * (1 - spread) / 1000) * 1000,
                                 round(yearly * (1 + spread) / 1000) * 1000, "year")
        row.update(salary_min=str(low), salary_max=str(high), salary_currency=currency, salary_period=period)
    return row


def make_defects(good_rows: list[dict], rng: random.Random, start_number: int) -> list[dict]:
    """Rows that validation must reject, plus exact and near duplicates it must collapse."""
    template = dict(good_rows[0])
    defects = []

    def variant(label: str, **changes) -> None:
        row = {**template, "source_job_id": f"SYN-{start_number + len(defects):04d}", **changes}
        defects.append(row)

    variant("no title", title="")
    variant("no company", company="")
    variant("bad date", posted_date="2026-13-45")
    variant("future date", posted_date="2099-01-01")
    variant("negative salary", salary_min="-5000", salary_max="90000", salary_currency="USD", salary_period="year")
    variant("inverted range", salary_min="120000", salary_max="90000", salary_currency="USD", salary_period="year")
    variant("no currency", salary_min="80000", salary_max="95000", salary_currency="", salary_period="year")
    variant("no period", salary_min="80000", salary_max="95000", salary_currency="USD", salary_period="")
    variant("short description", description="Hiring now.")
    variant("half a salary", salary_min="80000", salary_max="", salary_currency="USD", salary_period="year")
    for original in rng.sample(good_rows, 5):  # exact duplicates, same source id
        defects.append(dict(original))
    for original in rng.sample(good_rows, 4):  # same listing re-entered with different case/spacing
        defects.append({**original, "source_job_id": f"SYN-{start_number + len(defects):04d}",
                        "title": "  " + original["title"].upper() + " ",
                        "company": original["company"].lower()})
    return defects


def main() -> None:
    rng = random.Random(2026)
    good_rows = [make_job(rng, number) for number in range(1, 111)]
    rows = good_rows + make_defects(good_rows, rng, start_number=111)
    rng.shuffle(rows)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT}")


if __name__ == "__main__":
    main()
