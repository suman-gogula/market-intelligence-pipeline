-- Compare locations by volume, work mode, salary disclosure and skill density.
WITH skills_per_posting AS (
    SELECT job_id, COUNT(*) AS skill_count
    FROM job_skills
    GROUP BY job_id
)
SELECT
    p.data_origin,
    p.country,
    p.city,
    COUNT(*) AS postings,
    SUM(CASE WHEN p.work_mode = 'remote' THEN 1 ELSE 0 END) AS remote_postings,
    SUM(CASE WHEN p.work_mode = 'hybrid' THEN 1 ELSE 0 END) AS hybrid_postings,
    SUM(CASE WHEN p.work_mode = 'onsite' THEN 1 ELSE 0 END) AS onsite_postings,
    SUM(CASE WHEN p.salary_annual_min IS NOT NULL THEN 1 ELSE 0 END) AS postings_with_salary,
    ROUND(AVG(COALESCE(sp.skill_count, 0)), 1) AS avg_skills_per_posting
FROM job_postings AS p
LEFT JOIN skills_per_posting AS sp ON sp.job_id = p.job_id
GROUP BY p.data_origin, p.country, p.city
ORDER BY p.data_origin, postings DESC, p.country, p.city
