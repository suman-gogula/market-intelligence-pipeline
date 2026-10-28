# Data dictionary

## Input CSV columns (`sources.RAW_COLUMNS`)

Required: `title`, `company`, `posted_date`, `description`. All others are optional. Column names are case-insensitive. Unknown columns are ignored with a warning.

| Column | Format / rule |
|---|---|
| `source_job_id` | Your own ID. If empty, the content hash is used as the ID |
| `title`, `company` | Non-empty text (max 300 / 200 chars) |
| `location` | "City, Region, Country" or "Remote, Country". Last part = country, first = city |
| `work_mode` | remote, hybrid, onsite (aliases accepted). Empty + "Remote" in location = remote |
| `employment_type` | full_time, part_time, contract, internship (aliases accepted) |
| `posted_date` | `YYYY-MM-DD` (a time part is ignored). Not more than 1 day in the future |
| `salary_min`, `salary_max` | Both or neither. Non-negative numbers, commas allowed, min <= max |
| `salary_currency` | 3 letters |
| `salary_period` | hour, day, week, month, year. Required when salary is present |
| `description` | At least 30 characters. Truncated to 20,000 characters when stored |
| `source_url` | Optional link back to the listing |

Row numbers in `rejected_records` count data rows from 1 (the header is not counted).

## Tables

### `pipeline_runs`
| Column | Meaning |
|---|---|
| `run_id` | UTC timestamp + random suffix |
| `source_name`, `data_origin` | Where the rows came from; origin is `sample`, `user_csv` or `live` |
| `status` | `running`, `succeeded`, `failed` |
| `started_at`, `finished_at` | UTC |
| `rows_read`, `rows_rejected`, `rows_duplicate_in_batch`, `rows_inserted`, `rows_already_stored` | Counters; read = rejected + duplicate_in_batch + inserted + already_stored |
| `ai_enriched` | Postings labelled by AI in this run |
| `error_message` | Set only when failed (type and message, max 500 chars) |

### `job_postings`
| Column | Meaning |
|---|---|
| `job_id` | Hash of source name + source ID (or the content hash). Primary key |
| `content_hash` | Hash of normalised title, company, city, country, posted date. Unique |
| `source_name`, `data_origin`, `source_job_id`, `source_url` | Provenance |
| `title`, `title_normalized` | Cleaned title; lower-case, punctuation-free key |
| `company` | Cleaned company name |
| `location_raw`, `city`, `country` | Original text and parsed parts ("Not specified" / "Unknown" when absent) |
| `work_mode`, `employment_type` | Normalised categories (`unknown` when unrecognised) |
| `posted_date` | ISO date |
| `salary_currency` | Upper-case code, NULL when no salary |
| `salary_annual_min/max` | Annualised (hour x 2080, day x 260, week x 52, month x 12). Currencies are never converted |
| `description` | Cleaned text; line breaks collapse to spaces |
| `ai_category`, `ai_summary`, `ai_model`, `ai_enriched_at` | Optional AI output, NULL when not classified |
| `first_run_id`, `ingested_at` | Run that first stored the row, and when |

### `skill_catalog` / `job_skills`
`skill_catalog(skill, category)` is seeded from `skills.CATALOG` on every run. `job_skills(job_id, skill)` has one row per posting and skill found in title + description.

### `rejected_records`
`(run_id, row_number, reason, raw_record)`: the reasons joined with `; ` and the original row as JSON (description cut to 300 chars).

## Exported CSV files (`exports/<dir>/`)

`skill_demand`, `job_trends_monthly`, `top_skills_by_country`, `location_comparison`, `salary_summary`, `salary_by_skill`, `ai_categories`, `pipeline_runs`, `fact_job_postings`, `fact_job_skills`. All analytical files include `data_origin`.

## Known limits

- Skill matching is dictionary-based: it misses skills not in the catalogue, and cannot tell "used Python" from "Python is not required".
- Salary statistics are from postings that disclose a salary, which is not a random sample. Ranges are advertised, not paid, amounts.
- Moving averages run over months that have data; calendar gaps are not filled.
