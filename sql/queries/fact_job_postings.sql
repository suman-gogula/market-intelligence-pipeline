-- One row per posting, without the long description text, for BI tools.
SELECT
    job_id,
    data_origin,
    source_name,
    title,
    title_normalized,
    company,
    city,
    country,
    work_mode,
    employment_type,
    posted_date,
    salary_currency,
    salary_annual_min,
    salary_annual_max,
    ai_category
FROM job_postings
ORDER BY posted_date, job_id
