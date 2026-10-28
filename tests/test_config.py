import unittest

from market_intel.config import ConfigError, DEFAULT_DATABASE_URL, load_settings


class LoadSettingsTests(unittest.TestCase):
    def test_empty_environment_uses_safe_defaults(self):
        settings = load_settings({})
        self.assertEqual(settings.database_url, DEFAULT_DATABASE_URL)
        self.assertFalse(settings.ai_configured)
        self.assertEqual(settings.http_max_retries, 3)

    def test_blank_values_count_as_unset(self):
        settings = load_settings({"GEMINI_API_KEY": "   ", "LOG_LEVEL": ""})
        self.assertFalse(settings.ai_configured)
        self.assertEqual(settings.log_level, "INFO")

    def test_all_problems_are_reported_together(self):
        with self.assertRaises(ConfigError) as caught:
            load_settings({"DATABASE_URL": "mysql://x/y", "HTTP_TIMEOUT_SECONDS": "abc",
                           "HTTP_MAX_RETRIES": "99", "LOG_FORMAT": "xml"})
        message = str(caught.exception)
        for fragment in ("DATABASE_URL", "HTTP_TIMEOUT_SECONDS", "HTTP_MAX_RETRIES", "LOG_FORMAT"):
            self.assertIn(fragment, message)

    def test_postgres_url_requires_host(self):
        with self.assertRaises(ConfigError):
            load_settings({"DATABASE_URL": "postgresql:///onlyname"})

    def test_model_name_cannot_inject_url_parts(self):
        with self.assertRaises(ConfigError):
            load_settings({"GEMINI_MODEL": "x:generateContent?key=1/../"})

    def test_short_or_spaced_api_key_is_rejected_without_echoing_it(self):
        with self.assertRaises(ConfigError) as caught:
            load_settings({"GEMINI_API_KEY": "short key"})
        self.assertNotIn("short key", str(caught.exception))

    def test_secrets_are_listed_for_redaction_but_hidden_from_repr_and_describe(self):
        key = "k" * 30
        settings = load_settings({"GEMINI_API_KEY": key,
                                  "DATABASE_URL": "postgresql://user:s3cretpw@db.example.com/app"})
        self.assertIn(key, settings.secrets())
        self.assertIn("s3cretpw", settings.secrets())
        shown = repr(settings) + str(settings.describe())
        self.assertNotIn(key, shown)
        self.assertNotIn("s3cretpw", shown)
        self.assertEqual(settings.describe()["gemini_api_key"], "set")


if __name__ == "__main__":
    unittest.main()
