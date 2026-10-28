# Pre-publication security checklist

- [ ] `git status` shows no `.env`, `.venv/`, `*.db`, `data/local/` or `exports/latest/`.
- [ ] `.env.example` has an empty `GEMINI_API_KEY=` and no real URL or password.
- [ ] `python -m unittest tests.test_repo_hygiene` passes (scans for key, token, password-URL and personal-path patterns).
- [ ] `git log -p | findstr /i "AIza password secret"` finds nothing real (PowerShell: `git log -p | Select-String -Pattern "AIza|password|secret"`).
- - [ ] LICENSE contains your chosen copyright name without square brackets.
- [ ] No real personal data in `data/` or `exports/` (the bundled sample is synthetic).
- [ ] Any CSV you ingested stays outside the repository.
- [ ] Gemini key and database password exist only in `.env` and GitHub Actions secrets.
- [ ] Keys have the smallest scope and a usage cap where the provider offers one.
- [ ] You re-read the Remotive terms before publishing anything derived from live data.
- [ ] Billing is off or has a spending cap on every cloud account you connected.

## What the code does to protect secrets

- `Settings` hides keys and the database URL from `repr`; `check-config` prints them masked.
- Logs pass through a redaction filter that masks the API key and database password.
- The Gemini key is sent in a header, never in a URL, and URL query strings are never logged.
- All SQL uses bound parameters; the only dynamic SQL is a list of `:origin_N` placeholders built from a fixed code path.
- The model name from the environment is restricted to `[A-Za-z0-9._-]` before use in a URL.
- Job text sent to an LLM is wrapped in delimiters, the reply must match a fixed JSON shape and category list, and summaries are length-limited. This reduces, but does not eliminate, prompt-injection risk, so treat AI output as untrusted text.
