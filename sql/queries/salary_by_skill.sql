-- Average annualised salary midpoint per skill and currency.
-- Groups with fewer than 3 salary-bearing postings are hidden because an
-- average of one or two numbers is not a market signal.
SELECT
    p.data_origin,
    s.skill,
    p.salary_currency,
    COUNT(*) AS postings_with_salary,
    ROUND(AVG((p.salary_annual_min + p.salary_annual_max) / 2.0), 0) AS avg_annual_midpoint
FROM job_skills AS s
JOIN job_postings AS p ON p.job_id = s.job_id
WHERE p.salary_annual_min IS NOT NULL AND p.salary_annual_max IS NOT NULL
GROUP BY p.data_origin, s.skill, p.salary_currency
HAVING COUNT(*) >= 3
ORDER BY p.data_origin, p.salary_currency, avg_annual_midpoint DESC, s.skill
