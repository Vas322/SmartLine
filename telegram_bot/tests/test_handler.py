"""Tests for the Telegram update handler."""
from datetime import datetime
from unittest import mock

from django.test import SimpleTestCase, override_settings

from core.services.activity_service import ProcessResult, ProcessResultStatus
from telegram_bot.handler import handle_update


def _make_channel_post_update(
    *,
    update_id=1,
    message_id=10,
    chat_id=-1001234567890,
    text="Расписание на неделю",
    is_edit=False,
):
    """Create a channel_post or edited_channel_post update."""
    message = {
        "message_id": message_id,
        "chat": {"id": chat_id},
        "date": 1750000000,
        "text": text,
    }
    if is_edit:
        message["edit_date"] = 1750000001
        return {"update_id": update_id, "edited_channel_post": message}
    return {"update_id": update_id, "channel_post": message}


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


class ScheduleMirrorRoutingTests(SimpleTestCase):
    """Tests that schedule mirror messages are routed correctly."""

    @override_settings(SCHEDULE_SOURCE_CHAT_ID=-1001234567890, ALLIANCE_BOT_USERNAME="x5_fort_bot")
    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_channel_post_from_source_chat_routes_to_mirror_service(
        self, mock_process, mock_mirror
    ):
        """channel_post from SCHEDULE_SOURCE_CHAT_ID should go to mirror service, not activity service."""
        update = _make_channel_post_update(
            chat_id=-1001234567890,
            message_id=123,
            text="Расписание фортов на неделю...",
        )

        handle_update(update)

        mock_mirror.assert_called_once()
        mock_process.assert_not_called()
        kwargs = mock_mirror.call_args.kwargs
        self.assertEqual(kwargs["source_chat_id"], -1001234567890)
        self.assertEqual(kwargs["source_message_id"], 123)
        self.assertEqual(kwargs["text"], "Расписание фортов на неделю...")
        self.assertEqual(kwargs["alliance_bot_username"], "x5_fort_bot")
        self.assertFalse(kwargs["is_edit"])

    @override_settings(SCHEDULE_SOURCE_CHAT_ID=-1001234567890, ALLIANCE_BOT_USERNAME="x5_fort_bot")
    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    @mock.patch("telegram_bot.handler.process_telegram_edit")
    def test_edited_channel_post_from_source_chat_routes_to_mirror_service(
        self, mock_edit, mock_mirror
    ):
        """edited_channel_post from SCHEDULE_SOURCE_CHAT_ID should go to mirror service."""
        update = _make_channel_post_update(
            chat_id=-1001234567890,
            message_id=123,
            text="Обновлённое расписание фортов...",
            is_edit=True,
        )

        handle_update(update)

        mock_mirror.assert_called_once()
        mock_edit.assert_not_called()
        kwargs = mock_mirror.call_args.kwargs
        self.assertEqual(kwargs["source_chat_id"], -1001234567890)
        self.assertEqual(kwargs["source_message_id"], 123)
        self.assertEqual(kwargs["text"], "Обновлённое расписание фортов...")
        self.assertEqual(kwargs["alliance_bot_username"], "x5_fort_bot")
        self.assertTrue(kwargs["is_edit"])

    @override_settings(SCHEDULE_SOURCE_CHAT_ID=-1001234567890, ALLIANCE_BOT_USERNAME="x5_fort_bot")
    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_channel_post_from_different_chat_not_mirrored(
        self, mock_process, mock_mirror
    ):
        """channel_post from a different chat_id should not be mirrored."""
        update = _make_channel_post_update(
            chat_id=-999999999999,
            message_id=123,
            text="Расписание фортов на неделю...",
        )

        handle_update(update)

        mock_mirror.assert_not_called()
        mock_process.assert_not_called()


class RegistrationRoutingTests(SimpleTestCase):
    """Tests that registration messages are routed correctly."""

    def _make_registration_update(
        self,
        *,
        update_id=1,
        message_id=10,
        chat_id=1000,
        text="рега 2 кланами атака форта",
        has_photo=False,
    ):
        """Create a registration message update."""
        message = {
            "message_id": message_id,
            "chat": {"id": chat_id},
            "date": 1750000000,
            "text": text,
            "from": {"id": 500, "username": "swettka"},
        }
        if has_photo:
            message["photo"] = [{"file_id": "x", "width": 1, "height": 1}]
        return {"update_id": update_id, "message": message}

    @mock.patch("telegram_bot.handler.process_registration_message")
    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_registration_message_with_photo_routes_to_registration_service(
        self, mock_process_activity, mock_process_registration
    ):
        """Group message with text 'рега 2 кланами' and photo should route to registration service."""
        mock_process_registration.return_value = ProcessResult(
            status=ProcessResultStatus.REGISTRATION_CREATED,
            telegram_message=None,
        )

        update = self._make_registration_update(
            text="рега 2 кланами атака форта",
            has_photo=True,
        )

        handle_update(update)

        mock_process_registration.assert_called_once()
        mock_process_activity.assert_not_called()
        kwargs = mock_process_registration.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], 1000)
        self.assertEqual(kwargs["message_id"], 10)
        self.assertEqual(kwargs["user_id"], 500)
        self.assertEqual(kwargs["username"], "swettka")
        self.assertEqual(kwargs["text"], "рега 2 кланами атака форта")
        self.assertTrue(kwargs["has_photo"])
        self.assertEqual(kwargs["photo_file_id"], "x")
        self.assertIsInstance(kwargs["message_date"], datetime)

    @mock.patch("telegram_bot.handler.process_registration_message")
    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_regular_activity_message_not_routed_as_registration(
        self, mock_process_activity, mock_process_registration
    ):
        """Regular activity message '+1 | деф | Ник | опис' should NOT be routed as registration."""
        mock_process_activity.return_value = ProcessResult(
            status=ProcessResultStatus.ACTIVITY_CREATED,
            telegram_message=None,
        )

        update = self._make_registration_update(
            text="+1 | деф | Swettka | Первая волна",
            has_photo=False,
        )

        handle_update(update)

        mock_process_activity.assert_called_once()
        mock_process_registration.assert_not_called()

    @mock.patch("telegram_bot.handler.process_registration_message")
    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_regalia_not_routed_as_registration(
        self, mock_process_activity, mock_process_registration
    ):
        """Message 'регалия 2' should NOT be routed as registration (not a keyword)."""
        mock_process_activity.return_value = ProcessResult(
            status=ProcessResultStatus.IGNORED,
            telegram_message=None,
        )

        update = self._make_registration_update(
            text="регалия 2",
            has_photo=False,
        )

        handle_update(update)

        # Should go to activity service but be IGNORED (not a valid activity)
        mock_process_activity.assert_called_once()
        mock_process_registration.assert_not_called()
