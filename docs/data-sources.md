# Data sources, licensing and attribution

| Source | Origin label | Notes |
|---|---|---|
| `data/sample/sample_jobs.csv` | `sample` | Synthetic. Created for this repository, free to use under the project licence |
| Your own CSV | `user_csv` | You are responsible for having the right to use it. Do not commit it |
| Remotive public API | `live` | See below |

## Remotive

Remotive publishes a public jobs API (`https://remotive.com/api/remote-jobs`, no key). When this project was written, its documentation asked users to: keep requests low (a maximum of about four per day), credit Remotive and link back to the listing URL when showing jobs, and not submit Remotive's jobs to other job sites. Rules can change, so **read the current terms at https://remotive.com/remote-jobs/api before using it**.

How the project stays conservative:

- Live rows live only in your own database. They are never written into the repository (`data/local/` and `exports/*` except `exports/sample/` are git-ignored).
- The default workflow runs once a week, and retries are bounded.
- `source_url` is stored so a dashboard can link back to the listing.
- Live-origin descriptions are **not** sent to Gemini unless you pass `--include-live` to `enrich`.
- If you publish a dashboard built from live data, show aggregates and attribution, not copied listings.

The field mapping in `sources.py` follows Remotive's documented response (`id`, `url`, `title`, `company_name`, `job_type`, `publication_date`, `candidate_required_location`, `salary`, `description`). It was tested only against mocked responses; **it was not run against the live API** from the packaging environment.

## Not included

No scraped data, no third-party datasets, and no real personal information. Do not add job-board scraping to this project; most job boards forbid it in their terms.
