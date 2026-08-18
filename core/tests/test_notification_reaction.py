"""Unit tests for the best-effort Telegram reaction helper."""
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, override_settings

from core.services.notification_service import notify_activity_reaction
from telegram_bot.bot import TelegramAPIError

FAKE_TOKEN = "123456:FAKE_TOKEN_FOR_TESTS"


@override_settings(TELEGRAM_BOT_TOKEN=FAKE_TOKEN)
class NotifyActivityReactionTests(SimpleTestCase):
    def _message(self):
        return SimpleNamespace(telegram_chat_id=-100, telegram_message_id=5)

    def test_success_returns_true_and_sets_reaction(self):
        message = self._message()
        with mock.patch(
            "telegram_bot.bot.TelegramBot.set_message_reaction",
            return_value={"ok": True},
        ) as mock_reaction:
            result = notify_activity_reaction(message)
        self.assertTrue(result)
        mock_reaction.assert_called_once_with(
            chat_id=-100,
            message_id=5,
            emoji="🎉",
        )

    @override_settings(TELEGRAM_BOT_TOKEN="")
    def test_missing_token_returns_false_and_skips_api_call(self):
        message = self._message()
        with mock.patch(
            "telegram_bot.bot.TelegramBot.set_message_reaction",
        ) as mock_reaction:
            result = notify_activity_reaction(message)
        self.assertFalse(result)
        mock_reaction.assert_not_called()

    def test_api_error_returns_false_without_raising(self):
        message = self._message()
        with mock.patch(
            "telegram_bot.bot.TelegramBot.set_message_reaction",
            side_effect=TelegramAPIError(
                "Telegram setMessageReaction failed: HTTP 400"
            ),
        ):
            result = notify_activity_reaction(message)
        self.assertFalse(result)
