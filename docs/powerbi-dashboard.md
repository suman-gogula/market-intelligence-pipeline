# Power BI Desktop dashboard guide

Status: **unverified** -- Power BI Desktop is Windows-only and was not available when this project was packaged. The CSV files below were generated and checked by the pipeline; the Power BI steps follow standard Power BI behaviour, and menu names may differ slightly between versions. Screenshots are not included: take your own after building the report and save them in `docs/images/`.

## 1. Data

A ready-made export built from the **synthetic sample** is in `exports/sample/`. To export your own data: `python -m market_intel report --output-dir exports\latest`.

Files: `fact_job_postings.csv`, `fact_job_skills.csv`, plus pre-aggregated tables (`skill_demand`, `job_trends_monthly`, `location_comparison`, `salary_summary`, `salary_by_skill`, `top_skills_by_country`, `ai_categories`, `pipeline_runs`). Every analytical file has `data_origin`.

## 2. Load

1. Power BI Desktop > **Home > Get data > Text/CSV**.
2. Select `fact_job_postings.csv`, set *File origin* to UTF-8, choose **Transform Data**.
3. In Power Query make sure `posted_date` has type **Date** and salary columns are **Decimal number**. Close & Apply.
4. Repeat for `fact_job_skills.csv`, `skill_demand.csv`, `job_trends_monthly.csv`, `salary_summary.csv`.

## 3. Model

In **Model view** create one relationship: `fact_job_postings[job_id]` -> `fact_job_skills[job_id]` (one-to-many, single direction). The aggregated tables stand alone.

## 4. Measures (DAX)

```dax
Postings = DISTINCTCOUNT ( fact_job_postings[job_id] )
Remote Share = DIVIDE ( CALCULATE ( [Postings], fact_job_postings[work_mode] = "remote" ), [Postings] )
Postings With Salary = CALCULATE ( [Postings], NOT ISBLANK ( fact_job_postings[salary_annual_min] ) )
Salary Disclosure % = DIVIDE ( [Postings With Salary], [Postings] )
Avg Annual Midpoint =
    AVERAGEX ( FILTER ( fact_job_postings, NOT ISBLANK ( fact_job_postings[salary_annual_min] ) ),
               ( fact_job_postings[salary_annual_min] + fact_job_postings[salary_annual_max] ) / 2 )
```

## 5. Report page layout

| Visual | Fields |
|---|---|
| Slicers (top) | `data_origin`, `country`, `salary_currency` |
| Cards | Postings, Remote Share, Salary Disclosure % |
| Bar chart: top skills | `fact_job_skills[skill]` count of `job_id`, top 15 |
| Line chart: trend | `job_trends_monthly[posted_month]`, `postings`, `postings_3m_avg` |
| Table or map: locations | `location_comparison` country, city, postings |
| Bar chart: salary | `Avg Annual Midpoint` by country, **filtered to one currency** |
| Table | `pipeline_runs` (status, rows) |

Rules for an honest dashboard:
- Always show or filter by `data_origin`. Put "Synthetic sample data" in the title when it is `sample`.
- Never average salaries across currencies; the pipeline does not convert currencies.
- Show `postings_with_salary` next to any salary figure.
- For live Remotive data, credit Remotive and link `source_url`.

## 6. Refresh

After a new pipeline run, re-run `report`, then **Home > Refresh** in Power BI.
