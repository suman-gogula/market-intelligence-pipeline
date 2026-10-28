# Automated AI Market Intelligence Pipeline
GitHub repository: https://github.com/suman-gogula/market-intelligence-pipeline
- [View the dashboard preview (PDF)](market_intelligence_dashboard.pdf)
- [Download the Power BI report](market_intelligence_dashboard.pbix)
A Python/pandas data-engineering project that ingests job-market data, validates and cleans it, removes duplicates, extracts technical skills, stores everything in a SQL database (SQLite locally, PostgreSQL-compatible), and exports analytics for a Power BI dashboard. An optional Gemini step adds job categories and one-line summaries.

> **Data honesty:** the bundled dataset is **synthetic** (`data_origin = sample`). Live records can only enter through an explicit command and are labelled `live`. Nothing in this repository is a real job listing.

## What it does

1. **Ingest** from a local CSV or Remotive's public API (optional, live).
2. **Validate** each row; rejected rows and reasons are stored, never silently fixed.
3. **Clean and de-duplicate** (normalised text, locations, annualised salaries, content hashes).
4. **Extract skills** from titles and descriptions with a documented dictionary.
5. **Store** in SQL with constraints, an audit row per run, and safe reruns.
6. **Analyse** with SQL: skill demand, monthly trends, location comparison, salary data.
7. **Optionally label** postings with Gemini; the pipeline works fully without it.
8. **Export** CSVs for Power BI (`exports/sample/` is a ready-made example).

## Quick start (demo mode, no secrets)

Windows PowerShell (Linux/macOS: use `python3` and `source .venv/bin/activate`):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -e .
python -m unittest discover -s tests -t . -v
python -m market_intel demo --reset
```

Run `python -m market_intel demo` again: nothing new is inserted (safe rerun). Full guide: `docs/deployment.md`.

## Commands

| Command | Purpose |
|---|---|
| `python -m market_intel demo [--reset] [--ai]` | Load the synthetic sample into `data/local/demo.db` and export `exports/sample/` |
| `python -m market_intel ingest-csv FILE [--origin user_csv\|sample] [--ai]` | Ingest your CSV into `DATABASE_URL` |
| `python -m market_intel ingest-remotive [--category C] [--limit N]` | Live ingest from Remotive (read `docs/data-sources.md` first) |
| `python -m market_intel enrich [--max-jobs N] [--include-live]` | Label unlabelled postings with Gemini |
| `python -m market_intel report [--output-dir DIR]` | Export CSV analytics, print summary |
| `python -m market_intel init-db` / `check-config` | Create tables / validate configuration |

Exit codes: 0 success, 1 pipeline/source/database/API failure, 2 invalid configuration.

## Configuration

Copy `.env.example` to `.env` (optional). Every setting has a safe default; values are validated at startup. See `.env.example` for each variable. Never commit `.env`.

## Project layout

```
src/market_intel/   application code (see docs/architecture.md)
sql/schema.sql      tables, constraints, indexes
sql/queries/*.sql   analytical queries (skill demand, trends, locations, salaries...)
tests/              133 unittest tests, all external services mocked
data/sample/        synthetic dataset + README
exports/sample/     CSV export of the sample, for Power BI
scripts/            reproducible sample-data generator
docs/               architecture, workflow, data dictionary, deployment, Power BI, security, interview prep
.github/workflows/  CI and optional scheduled ingestion
```

## Architecture

```
CSV / API -> load -> validate -> clean + dedupe -> skills -> SQL database -> (optional AI) -> SQL queries -> CSV -> Power BI
```
Diagram with module responsibilities: `docs/architecture.md`.

## Sample output

Captured from `python -m market_intel demo --reset` (details in `docs/workflow.md`):

```text
Run 20261027T145059Z-8abcaf01  source=sample_jobs.csv  data_origin=sample
  rows read:             129
  rejected (invalid):    10
  duplicates in file:    9
  inserted:              110
```

## Screenshots

None are bundled: the packaging environment had no Power BI Desktop or browser. After building your report (`docs/powerbi-dashboard.md`), save screenshots to `docs/images/` and link them here.

## Data sources

Synthetic sample (included), your own CSV, and optionally Remotive's public API. Terms, attribution and limits: `docs/data-sources.md`. No scraping is used or supported.

## Testing

```powershell
python -m unittest discover -s tests -t . -v
```
Tests cover normal runs, malformed CSV, missing fields, duplicate ingestion and reruns, API failures and retries, database constraints and rollback, optional-AI failures, CLI exit codes, log redaction, and a repository hygiene scan for secrets. They need no network, API key or database server. PostgreSQL and the live Gemini/Remotive APIs are **not** exercised by the tests.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `python` not found on Windows | Reinstall Python with "Add to PATH", or use `py -3.12` |
| PowerShell refuses `Activate.ps1` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or use `activate.bat` in cmd |
| `ModuleNotFoundError: market_intel` | Activate the venv and run `python -m pip install -e .` from the project root |
| pandas fails to install | pandas 3 needs Python 3.11+; check `python --version` |
| `Invalid configuration:` | Fix the listed variables in `.env`; blank values are allowed |
| `PostgreSQL support needs the optional driver` | `python -m pip install -r requirements-postgres.txt` |
| `CSV file is malformed` | A row has more fields than the header; fix quoting in the file |
| Many rows rejected | Query `rejected_records` (see `docs/workflow.md`) for the reasons |
| AI labels all missing | Key not set, quota exceeded, or model name retired; the log shows `ai_job_failed`/`ai_skipped` |
| Remotive returns HTTP 429/5xx | Wait and retry later; stay within the source's stated limits |

## Security

See `docs/security-checklist.md` before publishing. The ZIP/repo contains no keys, no `.env`, no virtual environment and no real personal data.

## License

MIT The copyright holder and license terms are listed in LICENSE.. Chosen because it is short, widely understood, permissive for portfolio and employer review, and compatible with the dependencies used (pandas, requests and python-dotenv are permissively licensed). If you want patent-grant language, Apache-2.0 is the alternative. Dataset and generated content are synthetic and covered by the same licence.
