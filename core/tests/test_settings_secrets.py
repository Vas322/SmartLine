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