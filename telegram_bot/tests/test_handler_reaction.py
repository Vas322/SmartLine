"""Handler-level tests: bot reaction is set only for ACTIVITY_CREATED."""
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase

from core.services.activity_service import ProcessResult, ProcessResultStatus
from telegram_bot.handler import handle_update

FAKE_MESSAGE = SimpleNamespace(telegram_chat_id=-100, telegram_message_id=5)


def _make_update():
    return {
        "update_id": 1,
        "message": {
            "message_id": 5,
            "chat": {"id": -100},
            "text": "+1 | деф | Swettka | 13.00",
            "from": {"id": 1, "username": "x"},
            "date": 0,
        },
    }


def _make_edit_update():
    update = _make_update()
    update["edited_message"] = update.pop("message")
    update["edited_message"]["edit_date"] = 0
    return update


class HandlerReactionTests(SimpleTestCase):
    @mock.patch("telegram_bot.handler.notify_activity_reaction")
    @mock.patch(
        "telegram_bot.handler.process_telegram_message",
        return_value=ProcessResult(
            status=ProcessResultStatus.ACTIVITY_CREATED,
            telegram_message=FAKE_MESSAGE,
        ),
    )
    def test_activity_created_triggers_reaction(self, mock_process, mock_reaction):
        handle_update(_make_update())
        mock_reaction.assert_called_once_with(FAKE_MESSAGE, "👍")

    @mock.patch("telegram_bot.handler.notify_activity_reaction")
    @mock.patch(
        "telegram_bot.handler.process_telegram_message",
        return_value=ProcessResult(status=ProcessResultStatus.DUPLICATE),
    )
    def test_duplicate_does_not_trigger_reaction(self, mock_process, mock_reaction):
        handle_update(_make_update())
        mock_reaction.assert_not_called()

    @mock.patch("telegram_bot.handler.notify_activity_reaction")
    @mock.patch(
        "telegram_bot.handler.process_telegram_edit",
        return_value=ProcessResult(
            status=ProcessResultStatus.ACTIVITY_CREATED,
            telegram_message=FAKE_MESSAGE,
        ),
    )
    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_edited_activity_created_triggers_reaction(
        self, mock_process, mock_edit, mock_reaction
    ):
        handle_update(_make_edit_update())
        mock_reaction.assert_called_once_with(FAKE_MESSAGE, "👍")
