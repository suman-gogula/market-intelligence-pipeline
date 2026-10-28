# Deployment guide

Status legend: **Verified** = executed during packaging (Linux, Python 3.12.3). **Unverified** = written from documentation or reasoning, not executed.

## 1. Local setup on Windows with VS Code (commands unverified on Windows; the same steps were verified on Linux)

Requirements: Python 3.11 or newer from python.org (tick "Add python.exe to PATH"), VS Code with the Python extension.

```powershell
# 1. Extract the ZIP (File Explorer: right-click > Extract All, or:)
Expand-Archive -Path .\market-intelligence-pipeline.zip -DestinationPath .
cd .\market-intelligence-pipeline
code .

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install and test
python -m pip install -r requirements.txt
python -m pip install -e .
python -m unittest discover -s tests -t . -v

# 4. Run the demo (no secrets needed)
python -m market_intel demo --reset
```

If PowerShell blocks `Activate.ps1`: run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or use Command Prompt and `.venv\Scripts\activate.bat`.
In VS Code choose the interpreter with Ctrl+Shift+P > "Python: Select Interpreter" > `.venv`.

## 2. Using your own CSV

```powershell
python -m market_intel ingest-csv .\my_jobs.csv
python -m market_intel report --output-dir exports\latest
```

## 3. Free PostgreSQL (optional, unverified)

SQLite is enough for the demo and portfolio. To show PostgreSQL skills, use a free hosted instance.

**Neon (suggested).** At the time of writing, Neon's free plan offered roughly 0.5 GB storage per project and a monthly compute allowance, scaled the database to zero when idle, and suspended compute (rather than charging) when the free allowance ran out. Check https://neon.com/pricing for the current numbers and never add a payment method or upgrade the plan unless you intend to pay.

1. Create a Neon account and a project. Copy the connection string (it contains the password).
2. Put it in `.env` (never commit it): `DATABASE_URL=postgresql://USER:PASSWORD@HOST/DBNAME?sslmode=require`
3. `python -m pip install -r requirements-postgres.txt`
4. `python -m market_intel check-config` (the password is masked), then `python -m market_intel init-db`.
5. `python -m market_intel ingest-csv data\sample\sample_jobs.csv --origin sample`

Other free-tier Postgres hosts exist (for example Supabase). Compare their pause/inactivity rules and storage limits yourself before relying on them.

**What was and was not tested:** the SQL files avoid vendor-specific functions (checked by a test), and `:name` parameters are rewritten for psycopg by a unit-tested helper. No PostgreSQL server was available, so schema creation, the `ON CONFLICT` inserts and the analytical queries have **not** been run on PostgreSQL. Expect to fix small issues on first run, and add a CI job with a `postgres` service container once you have confirmed it locally.

## 4. Optional Gemini labels (unverified against the live API)

1. Create a key in Google AI Studio. Put it in `.env` as `GEMINI_API_KEY=...`.
2. Check the model name and free-tier limits shown in AI Studio, then set `GEMINI_MODEL` if the default is retired.
3. `python -m market_intel demo --reset --ai` or `python -m market_intel enrich --max-jobs 5`.

Risks: free-tier quotas are per project and change; requests beyond them fail (the pipeline logs and continues). Google's terms for free-tier use may allow your prompts to be used to improve its products, so send only public or synthetic text. Keep the key out of GitHub. Never enable billing on the Google Cloud project if you want to guarantee no charges.

## 5. GitHub Actions

- `ci.yml` -- tests and demo on each push. Needs no secrets. Standard runners are free for public repositories; private repositories get a monthly free-minute allowance, so check https://docs.github.com/billing for current limits.
- `scheduled-pipeline.yml` -- optional weekly live ingestion into your hosted PostgreSQL. It does nothing on schedule until you create the repository variable `ENABLE_SCHEDULED_RUN=true`. Add a repository secret `DATABASE_URL` (Settings > Secrets and variables > Actions). Use "Run workflow" to test it once by hand.
- GitHub pauses scheduled workflows in public repositories after a period without repository activity; re-enable them in the Actions tab if that happens.
- Neither workflow has been executed on GitHub (unverified). Action versions (`checkout@v4`, `setup-python@v5`) may have newer majors; update when GitHub warns.

## 6. Cost and quota summary

| Item | Cost risk | Guard in this project |
|---|---|---|
| GitHub Actions | Minutes on private repos | Short timeouts (10 min), no matrix on the scheduled job, weekly schedule |
| Remotive API | Rate/terms violations | `--limit`, bounded retries, weekly schedule |
| Gemini | Quota exhaustion, paid tiers | `GEMINI_MAX_JOBS_PER_RUN`, request spacing, stop after 3 consecutive failures, off unless `--ai` |
| Hosted PostgreSQL | Overages if you upgrade | Free plan only; small data; you control the plan |

Nothing here promises unlimited free usage. Free plans change, so re-check limits before each deployment.
