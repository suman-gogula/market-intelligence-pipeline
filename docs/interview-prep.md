# Interview preparation

Diagram: `architecture.md`. Walkthrough: `workflow.md`. Fields: `data-dictionary.md`.

## Your measurements (fill these in yourself -- do not quote numbers you have not measured)

| Metric | Value |
|---|---|
| Rows processed per second on your machine (`ingest-csv` with N rows) | `[TO MEASURE]` |
| Largest CSV you have ingested | `[TO MEASURE]` |
| Skill-extraction precision on 50 postings you labelled by hand | `[TO MEASURE]` |
| Gemini label agreement with your manual labels | `[TO MEASURE]` |
| Test count and runtime | run `python -m unittest discover -s tests -t . -v` |

## 20 technical questions

**1. Why separate validation from cleaning?**
Validation decides *whether* a row is acceptable and records why; cleaning decides *how* an accepted row is represented. Keeping them apart means bad data is rejected visibly instead of being silently "fixed", and each step can be tested alone. `validate.py` only reports reasons; `clean.py` assumes its input already passed.

**2. How does the pipeline make reruns safe?**
Two unique keys in `job_postings` (`job_id`, `content_hash`) plus `INSERT ... ON CONFLICT DO NOTHING`. A rerun inserts zero rows and reports them as "already stored". The insert's row count (1 or 0) tells the code which rows are new, so skills are only added for new rows.

**3. What is the difference between `job_id` and `content_hash`?**
`job_id` identifies a listing within a source (hash of source name + source ID, or the content hash if the source has no ID). `content_hash` identifies *the same listing regardless of source or ID*: normalised title, company, city, country and posted date. The second catches re-entered or cross-posted duplicates.

**4. Why a hash of normalised values and not fuzzy matching?**
It is deterministic, cheap, indexable and explainable. Its weakness: a slightly reworded title is not caught. Fuzzy matching (e.g. similarity thresholds) catches more but needs tuning and risks merging different jobs.

**5. Why one transaction per run?**
So a crash cannot leave half a file loaded. Data rows and the `succeeded` status commit together. The `running` row is committed first, in its own transaction, so a failed run is still visible; a separate transaction then marks it `failed`.

**6. Why does the pipeline use SQLite for the demo but support PostgreSQL?**
SQLite needs no server, so a beginner can run everything offline. The SQL is written in the common subset (no `strftime`, `to_char`, etc. -- a test checks this) and placeholders are rewritten for psycopg. The PostgreSQL path is implemented but was not executed in my environment, which I state openly.

**7. How do you prevent SQL injection?**
All values are bound parameters (`:name`). The one place SQL text is built dynamically is the `IN (...)` list in `enrich.py`, which only generates placeholder names (`:origin_0`...), never values. A test inserts a string containing `'; DROP TABLE` and checks it is stored as data.

**8. Why are CSV values read as text (`dtype=str`)?**
So pandas does not guess types: IDs with leading zeros stay intact, empty cells stay `""` rather than NaN, and every conversion happens in one place with a clear error message.

**9. How are salaries handled, and why no currency conversion?**
Salaries are annualised using fixed factors (hour x 2080, etc.) and stored with their currency. Without a dated exchange-rate source, converting would invent precision, so queries group by currency and never mix them. Rows with only one of min/max, a bad period, or an implausible annual amount are rejected.

**10. What are the limits of the skill extraction?**
It is dictionary-based with token-boundary regexes. It avoids classic traps ("Java" in "JavaScript", "SQL" in "NoSQL", "R&D", "go-getter") but cannot understand context ("Python not required"), misses skills outside the catalogue, and omits single-letter or ambiguous names such as R or Go (only "Golang" matches). Measure precision/recall on a hand-labelled sample before claiming accuracy.

**11. Why call Gemini through `requests` instead of an SDK?**
Fewer dependencies and full control over timeouts, retries and logging; the key travels in a header, not a URL. The cost is maintaining the request/response shapes myself. The Gemini integration was tested only against mocks.

**12. How is the AI step prevented from breaking the pipeline?**
It runs after ingestion has committed, each label is committed individually, `AiError`s are caught per job, three consecutive failures stop the run, and any unexpected exception is logged and swallowed at the pipeline level. Tests cover all of these.

**13. What risks come with sending job text to an LLM?**
Privacy (data leaves your machine; free tiers may use inputs for product improvement), terms of the data source (so live data is excluded by default), cost/quota, and prompt injection from untrusted text. Mitigations: opt-in flag, origin filter, delimiters, strict JSON/category validation, length limits.

**14. How do retries work and why are they bounded?**
`http_client.request_json` retries only transient failures (timeouts, connection errors, 429, 5xx), honours `Retry-After` (capped), uses exponential back-off, and makes at most `max_retries + 1` attempts. Unbounded retries can hammer an API and burn a free quota.

**15. Why is configuration validated at startup?**
To fail fast with every problem listed at once (exit code 2), instead of failing mid-run with a confusing error. Values have ranges (timeouts, retries), the model name is restricted to safe characters, and secrets are excluded from `repr` and logs.

**16. How do you stop secrets leaking into logs?**
A logging filter masks the registered secret values (API key, database password) in messages and fields. Keys are sent in headers, URL query strings are never logged, and `check-config` prints masked values. A test proves the masking in text and JSON modes.

**17. What does `ROW_NUMBER() OVER (PARTITION BY ...)` do in `top_skills_by_country.sql`?**
It numbers skills within each (origin, country) group by posting count, so `WHERE skill_rank <= 5` returns the top five per country. Ties are broken by skill name, which makes the output deterministic.

**18. Why does the monthly trend use a moving average over `ROWS`, not a date range?**
`ROWS BETWEEN 2 PRECEDING AND CURRENT ROW` is portable across SQLite and PostgreSQL. The trade-off: it averages the last three months *that have data*, so a calendar gap is not treated as zero.

**19. How do you distinguish sample from live data?**
A `data_origin` column with a CHECK constraint (`sample`, `user_csv`, `live`), set by the code path, carried into every query and export; the demo uses its own SQLite file; sample IDs start with `SYN-`; docs and the export note say so. Dashboards must filter or label by origin.

**20. What would you change to scale this to millions of rows?**
Replace row-by-row inserts with batched `COPY`/multi-row upserts, stream the CSV in chunks, add indexes based on measured query plans, move AI enrichment to a queue with rate limiting, schedule with an orchestrator (e.g. Airflow), and run the PostgreSQL tests in CI. Measure first; this project has no benchmarks yet.

## Design decisions you must be able to defend

1. Read everything as text; parse in one place.
2. Reject-and-record instead of silently repairing.
3. Two unique keys for duplicate detection (source ID and content hash).
4. One transaction per run; audit row committed separately.
5. `ON CONFLICT DO NOTHING` for idempotency, using the returned row count.
6. SQL kept in `.sql` files, one dialect-neutral subset for SQLite and PostgreSQL.
7. stdlib `sqlite3` + optional `psycopg` instead of an ORM (smaller, transparent; less portable tooling).
8. Dictionary-based skills instead of ML (explainable, testable; limited recall).
9. AI is optional, post-commit, bounded, opt-in per run, and excluded for live data by default.
10. No currency conversion; group by currency.
11. `data_origin` everywhere; demo isolated in its own database.
12. Unit tests with mocked HTTP and AI; no network in tests.
13. Honest status labels: verified versus unverified.
