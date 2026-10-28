-- Run history, newest first, so a dashboard can show pipeline health.
SELECT
    run_id,
    source_name,
    data_origin,
    status,
    started_at,
    finished_at,
    rows_read,
    rows_rejected,
    rows_duplicate_in_batch,
    rows_inserted,
    rows_already_stored,
    ai_enriched,
    error_message
FROM pipeline_runs
ORDER BY started_at DESC, run_id
