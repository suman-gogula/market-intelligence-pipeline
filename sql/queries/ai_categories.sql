-- Postings by AI-assigned category. Rows without a category were not classified.
SELECT
    data_origin,
    COALESCE(ai_category, 'not_classified') AS ai_category,
    COUNT(*) AS postings
FROM job_postings
GROUP BY data_origin, COALESCE(ai_category, 'not_classified')
ORDER BY data_origin, postings DESC, ai_category
