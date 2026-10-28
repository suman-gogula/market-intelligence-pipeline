"""Guards for publishing: no secrets, no machine-specific paths, required files present."""
import re
import unittest

from market_intel.paths import PROJECT_ROOT

SKIP_DIRS = {".git", ".venv", "__pycache__", "data/local"}
TEXT_SUFFIXES = {".py", ".md", ".txt", ".yml", ".yaml", ".toml", ".json", ".sql", ".csv", ".example", ""}
SECRET_PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "URL with password": re.compile(r"postgres(?:ql)?://[^:/\s]+:(?!PASSWORD|password|\*\*\*|%\()[^@\s]{3,}@"),
    "Windows user path": re.compile(r"[A-Za-z]:\\Users\\(?!YOUR|you|<)", re.I),
    "Linux home path": re.compile(r"/home/(?!you|user|runner)[a-z0-9_]+/"),
}


def project_files():
    for path in PROJECT_ROOT.rglob("*"):
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        if path.is_file() and not any(rel == d or rel.startswith(d + "/") or f"/{d}/" in f"/{rel}"
                                      for d in SKIP_DIRS) and path.suffix in TEXT_SUFFIXES \
                and not rel.endswith("test_repo_hygiene.py"):
            yield rel, path


class HygieneTests(unittest.TestCase):
    def test_no_secret_like_strings_or_personal_paths(self):
        for rel, path in project_files():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for label, pattern in SECRET_PATTERNS.items():
                if label == "URL with password" and rel.startswith("tests/"):
                    continue  # tests use obviously fake passwords to prove redaction works
                with self.subTest(file=rel, check=label):
                    self.assertIsNone(pattern.search(text), f"{label} found in {rel}")

    def test_no_real_env_file_is_present(self):
        self.assertFalse((PROJECT_ROOT / ".env").exists(), "remove .env before packaging")

    def test_env_example_has_empty_key_and_gitignore_protects_env(self):
        example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertRegex(example, r"(?m)^GEMINI_API_KEY=$")
        ignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        for entry in (".env", ".venv/", "__pycache__/", "data/local/", "*.db"):
            self.assertIn(entry, ignore)

    def test_required_deliverables_exist(self):
        for name in ("README.md", "LICENSE", "requirements.txt", ".gitignore", ".env.example",
                     "sql/schema.sql", "data/sample/sample_jobs.csv", "docs/architecture.md",
                     "docs/data-dictionary.md", "docs/deployment.md", "docs/powerbi-dashboard.md",
                     "docs/interview-prep.md", "docs/security-checklist.md"):
            self.assertTrue((PROJECT_ROOT / name).exists(), f"missing {name}")
        self.assertTrue(list((PROJECT_ROOT / ".github" / "workflows").glob("*.yml")))


if __name__ == "__main__":
    unittest.main()
