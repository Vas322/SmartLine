from pathlib import Path

from django.conf import settings
from django.test import TestCase

SETTINGS_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "settings.py"


class SettingsSecretsTestCase(TestCase):
    def test_no_hardcoded_secret_literals_in_source(self):
        text = SETTINGS_PATH.read_text(encoding="utf-8")
        self.assertNotIn("smartline", text)
        self.assertNotIn("unsafe-dev-key", text)

    def test_runtime_secrets_not_default(self):
        self.assertNotEqual(settings.DATABASES["default"]["PASSWORD"], "smartline")
        self.assertNotEqual(settings.SECRET_KEY, "unsafe-dev-key")


class SecuritySettingsTestCase(TestCase):
    def test_security_hardening_settings_present(self):
        # Hardcoded to True / safe string constants — always present
        self.assertEqual(settings.SECURE_CONTENT_TYPE_NOSNIFF, True)
        self.assertEqual(settings.SECURE_REFERRER_POLICY, "same-origin")
        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
        # Env-driven settings — just verify they exist and are the correct type
        self.assertIsInstance(settings.SECURE_SSL_REDIRECT, bool)
        self.assertIsInstance(settings.SECURE_HSTS_SECONDS, int)
        self.assertIsInstance(settings.SECURE_HSTS_INCLUDE_SUBDOMAINS, bool)
        self.assertIsInstance(settings.SECURE_HSTS_PRELOAD, bool)
