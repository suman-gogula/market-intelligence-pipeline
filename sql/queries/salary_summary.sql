-- Annualised salary ranges by country and currency, using only postings that disclose a salary.
-- Currencies are never mixed, because no exchange rates are applied.
SELECT
    data_origin,
    country,
    salary_currency,
    COUNT(*) AS postings_with_salary,
    ROUND(AVG(salary_annual_min), 0) AS avg_annual_min,
    ROUND(AVG(salary_annual_max), 0) AS avg_annual_max,
    MIN(salary_annual_min) AS lowest_annual_min,
    MAX(salary_annual_max) AS highest_annual_max
FROM job_postings
WHERE salary_annual_min IS NOT NULL AND salary_annual_max IS NOT NULL
GROUP BY data_origin, country, salary_currency
ORDER BY data_origin, country, salary_currency
