-- Schema for the market intelligence pipeline.
-- Written in the common subset of SQLite and PostgreSQL so one file serves both.
-- Statements are separated by semicolons and executed one by one, so keep
-- semicolons out of comments and string literals.

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id                  TEXT PRIMARY KEY,
    source_name             TEXT NOT NULL,
    data_origin             TEXT NOT NULL CHECK (data_origin IN ('sample', 'live', 'user_csv')),
    status                  TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    started_at              TIMESTAMP NOT NULL,
    finished_at             TIMESTAMP,
    rows_read               INTEGER NOT NULL DEFAULT 0,
    rows_rejected           INTEGER NOT NULL DEFAULT 0,
    rows_duplicate_in_batch INTEGER NOT NULL DEFAULT 0,
    rows_inserted           INTEGER NOT NULL DEFAULT 0,
    rows_already_stored     INTEGER NOT NULL DEFAULT 0,
    ai_enriched             INTEGER NOT NULL DEFAULT 0,
    error_message           TEXT
);

CREATE TABLE IF NOT EXISTS skill_catalog (
    skill    TEXT PRIMARY KEY,
    category TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS job_postings (
    job_id             TEXT PRIMARY KEY,
    content_hash       TEXT NOT NULL UNIQUE,
    source_name        TEXT NOT NULL,
    data_origin        TEXT NOT NULL CHECK (data_origin IN ('sample', 'live', 'user_csv')),
    source_job_id      TEXT,
    source_url         TEXT,
    title              TEXT NOT NULL,
    title_normalized   TEXT NOT NULL,
    company            TEXT NOT NULL,
    location_raw       TEXT,
    city               TEXT NOT NULL,
    country            TEXT NOT NULL,
    work_mode          TEXT NOT NULL CHECK (work_mode IN ('remote', 'hybrid', 'onsite', 'unknown')),
    employment_type    TEXT NOT NULL
        CHECK (employment_type IN ('full_time', 'part_time', 'contract', 'internship', 'unknown')),
    posted_date        DATE NOT NULL,
    salary_currency    TEXT,
    salary_annual_min  NUMERIC(14, 2),
    salary_annual_max  NUMERIC(14, 2),
    description        TEXT NOT NULL,
    ai_category        TEXT,
    ai_summary         TEXT,
    ai_model           TEXT,
    ai_enriched_at     TIMESTAMP,
    first_run_id       TEXT NOT NULL REFERENCES pipeline_runs (run_id),
    ingested_at        TIMESTAMP NOT NULL,
    CHECK (salary_annual_min IS NULL OR salary_annual_max IS NULL OR salary_annual_min <= salary_annual_max),
    CHECK ((salary_annual_min IS NULL) = (salary_annual_max IS NULL))
);

CREATE TABLE IF NOT EXISTS job_skills (
    job_id TEXT NOT NULL REFERENCES job_postings (job_id) ON DELETE CASCADE,
    skill  TEXT NOT NULL REFERENCES skill_catalog (skill),
    PRIMARY KEY (job_id, skill)
);

CREATE TABLE IF NOT EXISTS rejected_records (
    run_id     TEXT NOT NULL REFERENCES pipeline_runs (run_id),
    row_number INTEGER NOT NULL,
    reason     TEXT NOT NULL,
    raw_record TEXT NOT NULL,
    PRIMARY KEY (run_id, row_number)
);

CREATE INDEX IF NOT EXISTS idx_job_postings_posted_date ON job_postings (posted_date);

CREATE INDEX IF NOT EXISTS idx_job_postings_location ON job_postings (country, city);

CREATE INDEX IF NOT EXISTS idx_job_skills_skill ON job_skills (skill);
