# Sample execution walkthrough

Output below was produced by `python -m market_intel demo --reset` during packaging (Linux, Python 3.12.3).
Timestamps and run IDs differ on every run.

```text
DEMO MODE: synthetic sample data only, stored in the separate demo database.

Run 20261027T145059Z-8abcaf01  source=sample_jobs.csv  data_origin=sample
  rows read:             129
  rejected (invalid):    10
  duplicates in file:    9
  inserted:              110
  already stored:        0
  AI labels:             not requested

Top skills by share of postings (per data_origin):

  data_origin = sample
     skill  postings  pct_of_postings
    Python        56             50.9
    Docker        46             41.8
       Git        46             41.8
Kubernetes        38             34.5
       SQL        35             31.8
       AWS        31             28.2
JavaScript        29             26.4
     CI/CD        25             22.7
     Azure        24             21.8
PostgreSQL        24             21.8
```

## What each number means

1. **129 read** -- rows in `data/sample/sample_jobs.csv`.
2. **10 rejected** -- invalid rows (missing title/company, impossible or future date, negative or inverted salary, missing currency/period, too-short description, half a salary range). Reasons are in the `rejected_records` table.
3. **9 duplicates in file** -- 5 exact copies and 4 re-entered listings with different case/spacing/ID, collapsed by `job_id` / `content_hash`.
4. **110 inserted** -- 129 - 10 - 9.

Run `python -m market_intel demo` again (without `--reset`): *inserted* becomes 0 and *already stored* becomes 110. That is the safe-rerun behaviour.

## Inspect the rejected rows

```powershell
python -c "import sqlite3; c = sqlite3.connect('data/local/demo.db'); [print(r) for r in c.execute('select row_number, reason from rejected_records order by row_number')]"
```

## Step by step inside a run

1. `load_csv` reads every column as text (so `007` stays `007`) and checks required columns.
2. A `pipeline_runs` row with status `running` is committed.
3. `validate_rows` returns valid and rejected rows.
4. `clean_jobs` normalises text, parses locations, annualises salaries, computes hashes, drops duplicates and extracts skills.
5. One transaction inserts jobs, skills and rejected records and flips the run to `succeeded`.
6. Optional: `enrich_pending` asks Gemini to label up to N unlabelled postings.
7. `export_reports` runs each SQL file and writes a CSV.
