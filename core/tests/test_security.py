"""Tests for secret redaction in logs and token-free Telegram errors."""
import logging
import requests
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

import core.logging_utils as lu
from core.logging_utils import RedactingFilter, RedactingFormatter, redact
from core.services import notification_service
from telegram_bot.bot import TelegramAPIError, TelegramBot


class RedactUtilsTests(SimpleTestCase):
    def test_redact_masks_secrets(self):
        lu._secrets_cache.clear()
        with override_settings(
            TELEGRAM_BOT_TOKEN="12345:SECRETTKN",
            SECRET_KEY="supersecretkey",
            DATABASES={"default": {"PASSWORD": "dbpass"}},
        ):
            text = "token=12345:SECRETTKN key=supersecretkey pwd=dbpass"
            result = redact(text)
            self.assertNotIn("12345:SECRETTKN", result)
            self.assertNotIn("supersecretkey", result)
            self.assertNotIn("dbpass", result)
            self.assertIn(lu.REDACTED, result)
        lu._secrets_cache.clear()

    def test_redact_safe_when_no_secrets(self):
        lu._secrets_cache.clear()
        with override_settings(
            TELEGRAM_BOT_TOKEN="",
            SECRET_KEY="x",
            DATABASES={"default": {"PASSWORD": ""}},
        ):
            self.assertEqual(redact("hello world"), "hello world")
        lu._secrets_cache.clear()

    def test_redact_handles_empty_text(self):
        self.assertEqual(redact(""), "")
        self.assertEqual(redact(None), None)


class RedactingFilterTests(SimpleTestCase):
    def test_filter_redacts_msg_and_args(self):
        lu._secrets_cache.clear()
        with override_settings(TELEGRAM_BOT_TOKEN="12345:FILTERTKN"):
            record = logging.LogRecord(
                name="test",
                level=logging.ERROR,
                pathname=__file__,
                lineno=1,
                msg="token=%s request failed",
                args=("12345:FILTERTKN",),
                exc_info=None,
            )
            redacting = RedactingFilter()
            self.assertTrue(redacting.filter(record))
            self.assertNotIn("12345:FILTERTKN", record.msg)
            self.assertNotIn("12345:FILTERTKN", record.args)
        lu._secrets_cache.clear()


class RedactingFormatterTests(SimpleTestCase):
    def test_formatter_masks_exc_text(self):
        lu._secrets_cache.clear()
        with override_settings(TELEGRAM_BOT_TOKEN="12345:TOKENXYZ"):
            try:
                raise requests.exceptions.ConnectionError(
                    "Failed to connect to https://api.telegram.org/bot12345:TOKENXYZ/getUpdates"
                )
            except requests.exceptions.ConnectionError as exc:
                record = logging.LogRecord(
                    name="test",
                    level=logging.ERROR,
                    pathname=__file__,
                    lineno=1,
                    msg="poll error",
                    args=(),
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
                fmt = RedactingFormatter(fmt="{message}", style="{")
                out = fmt.format(record)
                self.assertNotIn("12345:TOKENXYZ", out)
                self.assertIn(lu.REDACTED, out)
        lu._secrets_cache.clear()


class NotificationLoggingTests(SimpleTestCase):
    def test_notify_kl_logs_no_token(self):
        with override_settings(
            TELEGRAM_BOT_TOKEN="12345:LEAKTKN",
            ADMIN_TELEGRAM_CHAT_IDS="999",
        ):
            with patch(
                "core.services.notification_service.requests.post",
                side_effect=requests.exceptions.RequestException(
                    "https://api.telegram.org/bot12345:LEAKTKN/sendMessage"
                ),
            ):
                with self.assertLogs(
                    logger="core.services.notification_service", level="ERROR"
                ) as cm:
                    notification_service.notify_kl("test message")
            full = "\n".join(cm.output)
            self.assertNotIn("12345:LEAKTKN", full)
            self.assertTrue(
                any(
                    "Failed to send Telegram notification" in line
                    for line in cm.output
                )
            )


class BotErrorTests(SimpleTestCase):
    def test_get_updates_raises_token_free_error(self):
        with override_settings(TELEGRAM_BOT_TOKEN="12345:LEAKTKN"):
            with patch(
                "telegram_bot.bot.requests.get",
                side_effect=requests.exceptions.ConnectionError(
                    "https://api.telegram.org/bot12345:LEAKTKN/getUpdates"
                ),
            ):
                bot = TelegramBot(token="12345:LEAKTKN")
                with self.assertRaises(TelegramAPIError) as ctx:
                    bot.get_updates()
                self.assertNotIn("12345:LEAKTKN", str(ctx.exception))

    def test_send_message_raises_token_free_error(self):
        with override_settings(TELEGRAM_BOT_TOKEN="12345:LEAKTKN"):
            with patch(
                "telegram_bot.bot.requests.post",
                side_effect=requests.exceptions.RequestException(
                    "https://api.telegram.org/bot12345:LEAKTKN/sendMessage"
                ),
            ):
                bot = TelegramBot(token="12345:LEAKTKN")
                with self.assertRaises(TelegramAPIError) as ctx:
                    bot.send_message(chat_id=999, text="hello")
                self.assertNotIn("12345:LEAKTKN", str(ctx.exception))
