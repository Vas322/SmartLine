"""Tests for the synchronous Telegram bot client error reporting."""
import unittest
from unittest import mock

import requests

from telegram_bot.bot import TelegramBot, TelegramAPIError


class FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.url = "https://api.telegram.org/botXXXX/getUpdates"  # без реального токена

    def raise_for_status(self):
        if self.status_code >= 400:
            err = requests.HTTPError(f"{self.status_code} Client Error for url: {self.url}")
            err.response = self
            raise err

    def json(self):
        return self._json


class TestGetUpdatesErrorReporting(unittest.TestCase):
    def _bot(self, token="12345:SECRETTKN"):
        return TelegramBot(token=token)

    def test_http_401_includes_status_and_description_without_token(self):
        resp = FakeResponse(401, {"ok": False, "description": "Unauthorized"})
        with mock.patch("telegram_bot.bot.requests.get", return_value=resp):
            with self.assertRaises(TelegramAPIError) as ctx:
                self._bot().get_updates()
        msg = str(ctx.exception)
        self.assertIn("401", msg)
        self.assertIn("Unauthorized", msg)
        self.assertNotIn("SECRETTKN", msg)

    def test_ok_false_returns_description_without_token(self):
        resp = FakeResponse(200, {"ok": False, "description": "something wrong"})
        with mock.patch("telegram_bot.bot.requests.get", return_value=resp):
            with self.assertRaises(TelegramAPIError) as ctx:
                self._bot().get_updates()
        msg = str(ctx.exception)
        self.assertIn("something wrong", msg)
        self.assertNotIn("SECRETTKN", msg)

    def test_connection_error_reported_without_token(self):
        with mock.patch(
            "telegram_bot.bot.requests.get",
            side_effect=requests.ConnectionError("failed to connect"),
        ):
            with self.assertRaises(TelegramAPIError) as ctx:
                self._bot().get_updates()
        msg = str(ctx.exception)
        self.assertIn("ConnectionError", msg)
        self.assertNotIn("SECRETTKN", msg)

    def test_ok_response_returns_result(self):
        resp = FakeResponse(200, {"ok": True, "result": [{"update_id": 1}]})
        with mock.patch("telegram_bot.bot.requests.get", return_value=resp):
            result = self._bot().get_updates()
        self.assertEqual(result, [{"update_id": 1}])


class TestSendMessageErrorReporting(unittest.TestCase):
    def test_http_error_includes_status_without_token(self):
        resp = FakeResponse(403, {"ok": False, "description": "Forbidden: bot was blocked"})
        with mock.patch("telegram_bot.bot.requests.post", return_value=resp):
            with self.assertRaises(TelegramAPIError) as ctx:
                TelegramBot(token="12345:SECRETTKN").send_message(1, "hi")
        msg = str(ctx.exception)
        self.assertIn("403", msg)
        self.assertIn("Forbidden", msg)
        self.assertNotIn("SECRETTKN", msg)


class TestPollErrorLogging(unittest.TestCase):
    def test_polling_error_logs_message_not_just_class(self):
        from django.core.management import call_command

        with mock.patch(
            "telegram_bot.management.commands.poll.TelegramBot"
        ) as bot_mock, mock.patch(
            "telegram_bot.management.commands.poll.time.sleep",
            side_effect=KeyboardInterrupt,
        ):
            instance = bot_mock.return_value
            instance.get_updates.side_effect = TelegramAPIError("HTTP 401: Unauthorized")
            with self.assertLogs(
                "telegram_bot.management.commands.poll", level="ERROR"
            ) as cm:
                try:
                    call_command("poll")
                except KeyboardInterrupt:
                    pass
            self.assertTrue(
                any("HTTP 401: Unauthorized" in line for line in cm.output)
            )