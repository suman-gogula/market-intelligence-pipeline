-- The five most requested skills in each country, using a ranking window function.
WITH skill_counts AS (
    SELECT p.data_origin, p.country, s.skill, COUNT(*) AS postings
    FROM job_skills AS s
    JOIN job_postings AS p ON p.job_id = s.job_id
    GROUP BY p.data_origin, p.country, s.skill
),
ranked AS (
    SELECT
        data_origin,
        country,
        skill,
        postings,
        ROW_NUMBER() OVER (
            PARTITION BY data_origin, country
            ORDER BY postings DESC, skill
        ) AS skill_rank
    FROM skill_counts
)
SELECT data_origin, country, skill_rank, skill, postings
FROM ranked
WHERE skill_rank <= 5
ORDER BY data_origin, country, skill_rank
