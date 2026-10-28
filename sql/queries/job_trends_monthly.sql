-- Postings per posting month with remote share and a 3-row moving average.
-- The moving average runs over the months that have data, so a gap in the
-- calendar is not filled with zeros.
WITH monthly AS (
    SELECT
        data_origin,
        SUBSTR(CAST(posted_date AS TEXT), 1, 7) AS posted_month,
        COUNT(*) AS postings,
        SUM(CASE WHEN work_mode = 'remote' THEN 1 ELSE 0 END) AS remote_postings,
        SUM(CASE WHEN salary_annual_min IS NOT NULL THEN 1 ELSE 0 END) AS postings_with_salary
    FROM job_postings
    GROUP BY data_origin, SUBSTR(CAST(posted_date AS TEXT), 1, 7)
)
SELECT
    data_origin,
    posted_month,
    postings,
    remote_postings,
    ROUND(100.0 * remote_postings / postings, 1) AS remote_pct,
    postings_with_salary,
    ROUND(AVG(postings) OVER (
        PARTITION BY data_origin
        ORDER BY posted_month
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ), 1) AS postings_3m_avg
FROM monthly
ORDER BY data_origin, posted_month
