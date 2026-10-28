-- How many postings mention each skill, as a share of all postings from the same origin.
WITH totals AS (
    SELECT data_origin, COUNT(*) AS total_postings
    FROM job_postings
    GROUP BY data_origin
)
SELECT
    p.data_origin,
    c.category,
    s.skill,
    COUNT(*) AS postings,
    t.total_postings,
    ROUND(100.0 * COUNT(*) / t.total_postings, 1) AS pct_of_postings
FROM job_skills AS s
JOIN skill_catalog AS c ON c.skill = s.skill
JOIN job_postings AS p ON p.job_id = s.job_id
JOIN totals AS t ON t.data_origin = p.data_origin
GROUP BY p.data_origin, c.category, s.skill, t.total_postings
ORDER BY p.data_origin, postings DESC, s.skill
