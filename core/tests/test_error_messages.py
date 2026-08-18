"""Tests for friendly Russian error messages and their use in notifications."""
from unittest.mock import patch

from django.utils import timezone

from django.test import SimpleTestCase, TestCase

from core.error_messages import friendly_error_message
from core.models import ProcessingError, TelegramMessage
from core.services import notification_service


class FriendlyErrorMessageTests(SimpleTestCase):
    def test_invalid_amount(self):
        self.assertIn("час", friendly_error_message("invalid_amount"))

    def test_invalid_activity_type(self):
        self.assertIn("деф", friendly_error_message("invalid_activity_type"))

    def test_invalid_wave_time(self):
        self.assertIn("волн", friendly_error_message("invalid_wave_time"))

    def test_missing_wave_time(self):
        self.assertIn("врем", friendly_error_message("missing_wave_time"))

    def test_empty_nickname(self):
        self.assertIn("ник", friendly_error_message("empty_nickname"))

    def test_message_does_not_start_with_plus(self):
        self.assertIn("«+»", friendly_error_message("message_does_not_start_with_plus"))

    def test_player_conflict_includes_nick(self):
        msg = friendly_error_message("nickname_registered_to_other_telegram:Swettka")
        self.assertIn("Swettka", msg)
        self.assertIn("друг", msg)

    def test_unknown_reason_falls_back_with_code(self):
        msg = friendly_error_message("some_future_code")
        self.assertIn("some_future_code", msg)


class NotifyProcessingErrorTests(TestCase):
    def test_uses_friendly_message_not_raw_code(self):
        msg = TelegramMessage.objects.create(
            telegram_chat_id=-100,
            telegram_message_id=1,
            text="+1 | деф | Swettka",
            message_date=timezone.now(),
        )
        err = ProcessingError.objects.create(
            telegram_message=msg,
            reason="missing_wave_time",
            status=ProcessingError.Status.NEW,
        )
        with patch.object(
            notification_service, "notify_group_reply", return_value=True
        ) as mock_reply:
            notification_service.notify_processing_error(err)
            sent_text = mock_reply.call_args[0][1]
        self.assertIn("Не указано время начала волны", sent_text)
        self.assertNotIn("missing_wave_time", sent_text)
        err.refresh_from_db()
        self.assertEqual(err.status, ProcessingError.Status.NOTIFIED)