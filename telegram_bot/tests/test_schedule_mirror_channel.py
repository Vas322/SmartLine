"""Tests for schedule mirror handling of channel_post / edited_channel_post updates."""
from datetime import datetime
from unittest import mock

from django.test import SimpleTestCase, override_settings

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


@override_settings(
    TELEGRAM_BOT_TOKEN="12345:TESTTOKEN",
    SCHEDULE_SOURCE_CHAT_ID=-1001234567890,
    ALLIANCE_BOT_USERNAME="x5_fort_bot",
    CLAN_CHAT_ID=-1000000000,
    SCHEDULE_MIRROR_IGNORE_PREFIXES=["test", "тест", "/refresh", "/fix"],
)
class ScheduleMirrorChannelTests(SimpleTestCase):
    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    def test_channel_post_from_source_chat_calls_mirror_service(self, mock_mirror):
        """channel_post from SCHEDULE_SOURCE_CHAT_ID should call handle_source_message."""
        update = _make_channel_post_update(
            chat_id=-1001234567890,
            message_id=100,
            text="Расписание фортов на неделю...",
        )

        handle_update(update)

        mock_mirror.assert_called_once()
        kwargs = mock_mirror.call_args.kwargs
        self.assertEqual(kwargs["source_chat_id"], -1001234567890)
        self.assertEqual(kwargs["source_message_id"], 100)
        self.assertEqual(kwargs["text"], "Расписание фортов на неделю...")
        self.assertEqual(kwargs["alliance_bot_username"], "x5_fort_bot")
        self.assertFalse(kwargs["is_edit"])

    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    def test_edited_channel_post_from_source_chat_calls_mirror_service_with_is_edit(self, mock_mirror):
        """edited_channel_post from SCHEDULE_SOURCE_CHAT_ID should call handle_source_message with is_edit=True."""
        update = _make_channel_post_update(
            chat_id=-1001234567890,
            message_id=100,
            text="Обновлённое расписание фортов...",
            is_edit=True,
        )

        handle_update(update)

        mock_mirror.assert_called_once()
        kwargs = mock_mirror.call_args.kwargs
        self.assertEqual(kwargs["source_chat_id"], -1001234567890)
        self.assertEqual(kwargs["source_message_id"], 100)
        self.assertEqual(kwargs["text"], "Обновлённое расписание фортов...")
        self.assertEqual(kwargs["alliance_bot_username"], "x5_fort_bot")
        self.assertTrue(kwargs["is_edit"])

    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    def test_channel_post_with_slash_command_skipped(self, mock_mirror):
        """channel_post starting with '/' should be skipped (denylist)."""
        update = _make_channel_post_update(
            chat_id=-1001234567890,
            message_id=100,
            text="/refresh schedule",
        )

        handle_update(update)

        mock_mirror.assert_not_called()

    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    def test_channel_post_with_test_prefix_skipped(self, mock_mirror):
        """channel_post starting with 'test' should be skipped (denylist)."""
        update = _make_channel_post_update(
            chat_id=-1001234567890,
            message_id=100,
            text="test message for schedule",
        )

        handle_update(update)

        mock_mirror.assert_not_called()

    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    def test_channel_post_with_cyrillic_test_prefix_skipped(self, mock_mirror):
        """channel_post starting with 'тест' should be skipped (denylist)."""
        update = _make_channel_post_update(
            chat_id=-1001234567890,
            message_id=100,
            text="тест проверка расписания",
        )

        handle_update(update)

        mock_mirror.assert_not_called()

    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    def test_channel_post_with_fix_prefix_skipped(self, mock_mirror):
        """channel_post starting with '/fix' should be skipped (denylist)."""
        update = _make_channel_post_update(
            chat_id=-1001234567890,
            message_id=100,
            text="/fix something",
        )

        handle_update(update)

        mock_mirror.assert_not_called()

    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    def test_channel_post_empty_text_skipped(self, mock_mirror):
        """channel_post with empty text should be skipped."""
        update = _make_channel_post_update(
            chat_id=-1001234567890,
            message_id=100,
            text="",
        )

        handle_update(update)

        mock_mirror.assert_not_called()

    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    def test_channel_post_from_different_chat_not_mirrored(self, mock_mirror):
        """channel_post from a different chat_id should not be mirrored."""
        update = _make_channel_post_update(
            chat_id=-999999999999,
            message_id=100,
            text="Расписание фортов...",
        )

        handle_update(update)

        mock_mirror.assert_not_called()

    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    def test_channel_post_case_insensitive_denylist(self, mock_mirror):
        """Denylist check should be case-insensitive."""
        for prefix in ["TEST", "Test", "Тест", "ТЕСТ", "/REFRESH", "/Refresh", "/FIX", "/Fix"]:
            with self.subTest(prefix=prefix):
                mock_mirror.reset_mock()
                update = _make_channel_post_update(
                    chat_id=-1001234567890,
                    message_id=100,
                    text=f"{prefix} some schedule",
                )
                handle_update(update)
                mock_mirror.assert_not_called()

    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    def test_denylist_only_at_start_of_text(self, mock_mirror):
        """Denylist prefixes should only match at the start of text (after whitespace)."""
        # These should NOT be skipped (denylist word in middle)
        for text in ["some test message", "schedule /refresh now", "this is a test"]:
            with self.subTest(text=text):
                mock_mirror.reset_mock()
                update = _make_channel_post_update(
                    chat_id=-1001234567890,
                    message_id=100,
                    text=text,
                )
                handle_update(update)
                mock_mirror.assert_called_once()

        # These SHOULD be skipped (denylist word at start)
        for text in ["test message", " тест with space", "  /refresh now"]:
            with self.subTest(text=text):
                mock_mirror.reset_mock()
                update = _make_channel_post_update(
                    chat_id=-1001234567890,
                    message_id=100,
                    text=text,
                )
                handle_update(update)
                mock_mirror.assert_not_called()

    @mock.patch("telegram_bot.handler.schedule_mirror_service.handle_source_message")
    def test_channel_post_exception_does_not_break_flow(self, mock_mirror):
        """Exception in mirror service should be caught and not propagate."""
        mock_mirror.side_effect = Exception("Telegram API error")

        # Should not raise
        update = _make_channel_post_update(
            chat_id=-1001234567890,
            message_id=100,
            text="Расписание фортов...",
        )
        handle_update(update)

        mock_mirror.assert_called_once()