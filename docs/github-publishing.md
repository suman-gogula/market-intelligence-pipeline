# Publishing to GitHub (beginner guide)

Complete `security-checklist.md` first.

1. Install Git for Windows and create a GitHub account.
2. In the project folder (VS Code terminal):

```powershell
git init -b main
git config user.name "GOGULA VENKATA SUMAN"
git config user.email "sumangogula33@gmail.com"   # or your GitHub no-reply address
git add .
git status          # read this list: there must be no .env, .venv, .db or exports other than exports/sample
git commit -m "Initial commit: market intelligence pipeline"
```

3. On github.com click **New repository**, name it `market-intelligence-pipeline`, leave it empty (no README/licence), then:

```powershell
git remote add origin https://github.com/suman-gogula/market-intelligence-pipeline.git
git push -u origin main
```

4. Replace Confirm your copyright name is set in LICENSE, then add your GitHub repository link to README.md.
5. Open the **Actions** tab and confirm the CI run is green. (Unverified: I could not run GitHub Actions.)
6. Add your own screenshots to `docs/images/` and link them in the README (see `powerbi-dashboard.md`).
7. In repository **Settings > Secrets and variables > Actions**, add `DATABASE_URL` only if you plan to use the scheduled workflow.

If you ever commit a secret by mistake: revoke/rotate it immediately at the provider. Deleting the commit is not enough because the history stays public.
