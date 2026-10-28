-- One row per posting and skill, with the skill category, for BI tools.
SELECT
    s.job_id,
    s.skill,
    c.category AS skill_category
FROM job_skills AS s
JOIN skill_catalog AS c ON c.skill = s.skill
ORDER BY s.job_id, s.skill
