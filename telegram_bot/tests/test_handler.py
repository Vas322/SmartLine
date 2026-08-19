"""Tests for the Telegram update handler."""
from datetime import datetime
from unittest import mock

from django.test import SimpleTestCase

from telegram_bot.handler import handle_update


def _make_update(
    *,
    update_id=1,
    message_id=10,
    chat_id=1000,
    text="+1 | деф | Swettka | Первая волна",
    caption="+1 | деф | Swettka | Первая волна",
    has_from=True,
    has_text=True,
    has_caption=False,
    has_photo=False,
    has_message=True,
):
    message = {}
    if has_message:
        message["message_id"] = message_id
        message["chat"] = {"id": chat_id}
        message["date"] = 1750000000
        if has_from:
            message["from"] = {"id": 500, "username": "swettka"}
        if has_photo:
            message["photo"] = [{"file_id": "x", "width": 1, "height": 1}]
        if has_text:
            message["text"] = text
        else:
            message.pop("text", None)
        if has_caption:
            message["caption"] = caption
        else:
            message.pop("caption", None)
    return {"update_id": update_id, "message": message}


def _make_edit_update(**kwargs):
    update = _make_update(**kwargs)
    update["edited_message"] = update.pop("message")
    update["edited_message"]["edit_date"] = 1750000001
    return update


class HandleUpdateTests(SimpleTestCase):
    @mock.patch("telegram_bot.handler.process_telegram_edit")
    @mock.patch(
        "telegram_bot.handler.process_telegram_message",
        return_value=mock.Mock(status=mock.Mock(value="OK")),
    )
    def test_valid_update_calls_service(self, mock_process, mock_edit):
        handle_update(_make_update())
        mock_process.assert_called_once()
        mock_edit.assert_not_called()
        kwargs = mock_process.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], 1000)
        self.assertEqual(kwargs["message_id"], 10)
        self.assertEqual(kwargs["user_id"], 500)
        self.assertEqual(kwargs["username"], "swettka")
        self.assertEqual(kwargs["text"], "+1 | деф | Swettka | Первая волна")
        self.assertIsInstance(kwargs["message_date"], datetime)

    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_update_without_message_is_ignored(self, mock_process):
        handle_update({"update_id": 1})
        mock_process.assert_not_called()

    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_message_without_text_is_ignored(self, mock_process):
        handle_update(_make_update(has_text=False))
        mock_process.assert_not_called()

    @mock.patch(
        "telegram_bot.handler.process_telegram_message",
        return_value=mock.Mock(status=mock.Mock(value="OK")),
    )
    def test_missing_username_passes_empty(self, mock_process):
        update = _make_update()
        update["message"]["from"] = {"id": 500}
        handle_update(update)
        kwargs = mock_process.call_args.kwargs
        self.assertEqual(kwargs["username"], "")

    @mock.patch(
        "telegram_bot.handler.process_telegram_edit",
        return_value=mock.Mock(status=mock.Mock(value="OK")),
    )
    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_edited_message_calls_edit_service(self, mock_process, mock_edit):
        handle_update(_make_edit_update())
        mock_edit.assert_called_once()
        mock_process.assert_not_called()
        kwargs = mock_edit.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], 1000)
        self.assertEqual(kwargs["message_id"], 10)
        self.assertEqual(kwargs["user_id"], 500)
        self.assertEqual(kwargs["username"], "swettka")
        self.assertEqual(kwargs["text"], "+1 | деф | Swettka | Первая волна")
        self.assertIsInstance(kwargs["message_date"], datetime)

    @mock.patch(
        "telegram_bot.handler.process_telegram_edit",
        return_value=mock.Mock(status=mock.Mock(value="OK")),
    )
    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_edited_message_without_text_is_ignored(self, mock_process, mock_edit):
        update = _make_edit_update(has_text=False)
        handle_update(update)
        mock_edit.assert_not_called()
        mock_process.assert_not_called()

    @mock.patch(
        "telegram_bot.handler.process_telegram_message",
        return_value=mock.Mock(status=mock.Mock(value="OK")),
    )
    def test_photo_with_caption_activity_is_processed(self, mock_process):
        update = _make_update(
            has_text=False,
            has_caption=True,
            caption="+1 | деф | Swettka | Первая волна",
            has_photo=True,
        )
        handle_update(update)
        mock_process.assert_called_once()
        self.assertEqual(
            mock_process.call_args.kwargs["text"],
            "+1 | деф | Swettka | Первая волна",
        )

    @mock.patch(
        "telegram_bot.handler.process_telegram_message",
        return_value=mock.Mock(status=mock.Mock(value="OK")),
    )
    def test_photo_with_caption_non_activity_forwards_to_service(self, mock_process):
        update = _make_update(
            has_text=False,
            has_caption=True,
            caption="просто текст",
            has_photo=True,
        )
        handle_update(update)
        mock_process.assert_called_once()
        self.assertEqual(
            mock_process.call_args.kwargs["text"],
            "просто текст",
        )

    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_photo_without_caption_is_ignored(self, mock_process):
        update = _make_update(has_text=False, has_photo=True)
        handle_update(update)
        mock_process.assert_not_called()

    @mock.patch(
        "telegram_bot.handler.process_telegram_edit",
        return_value=mock.Mock(status=mock.Mock(value="OK")),
    )
    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_edited_photo_with_caption_calls_edit(self, mock_process, mock_edit):
        update = _make_edit_update(
            has_text=False,
            has_caption=True,
            caption="+1 | деф | Swettka | Первая волна",
            has_photo=True,
        )
        handle_update(update)
        mock_edit.assert_called_once()
        mock_process.assert_not_called()
        self.assertEqual(
            mock_edit.call_args.kwargs["text"],
            "+1 | деф | Swettka | Первая волна",
        )
