# Sample data (synthetic)

`sample_jobs.csv` is **entirely synthetic**. No row describes a real job, company
or person. Company names are fictional, descriptions are assembled from templates,
and every `source_job_id` starts with `SYN-`.

It was produced by `scripts/generate_sample_data.py` with a fixed random seed, so
it can be regenerated identically. It deliberately includes:

- 10 invalid rows (missing title/company, bad and future dates, bad salary data, a too-short description)
- 5 exact duplicates and 4 near-duplicates (same listing, different case/spacing/ID)

so the validation and duplicate-detection steps have something to show.
The pipeline always stores these rows with `data_origin = 'sample'`.
