"""Tests for the cleanup_old_messages management command."""
from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.models import Activity, Player, Registration, TelegramMessage


class CleanupOldMessagesTests(TestCase):
    """Tests for deleting old regular Telegram messages."""

    def _make_message(self, text: str, days_old: int, status=None) -> TelegramMessage:
        tm = TelegramMessage.objects.create(
            telegram_chat_id=1,
            telegram_message_id=TelegramMessage.objects.count() + 1,
            telegram_username="test_user",
            text=text,
            message_date=timezone.now() - timedelta(days=days_old),
            status=status or TelegramMessage.Status.REGULAR,
        )
        TelegramMessage.objects.filter(pk=tm.pk).update(
            created_at=timezone.now() - timedelta(days=days_old)
        )
        tm.refresh_from_db()
        return tm

    def test_regular_older_than_days_is_deleted(self):
        self._make_message("Обычное сообщение", days_old=20)
        call_command("cleanup_old_messages", days=14)
        self.assertEqual(TelegramMessage.objects.count(), 0)

    def test_regular_newer_than_days_is_not_deleted(self):
        self._make_message("Обычное сообщение", days_old=5)
        call_command("cleanup_old_messages", days=14)
        self.assertEqual(TelegramMessage.objects.count(), 1)

    def test_plus_text_older_than_days_is_not_deleted(self):
        self._make_message("+1 | деф | Swettka | описание", days_old=20)
        call_command("cleanup_old_messages", days=14)
        self.assertEqual(TelegramMessage.objects.count(), 1)

    def test_rega_text_older_than_days_is_not_deleted(self):
        self._make_message("рега 2 кланами", days_old=20)
        call_command("cleanup_old_messages", days=14)
        self.assertEqual(TelegramMessage.objects.count(), 1)

    def test_registration_text_older_than_days_is_not_deleted(self):
        self._make_message("регистрация клана на форт", days_old=20)
        call_command("cleanup_old_messages", days=14)
        self.assertEqual(TelegramMessage.objects.count(), 1)

    def test_processed_with_activity_is_not_deleted(self):
        player = Player.objects.create(nickname="Swettka")
        tm = self._make_message("+1 | деф | Swettka | описание", days_old=20, status=TelegramMessage.Status.PROCESSED)
        Activity.objects.create(
            player=player,
            telegram_message=tm,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            description="описание",
        )
        call_command("cleanup_old_messages", days=14)
        self.assertEqual(TelegramMessage.objects.count(), 1)

    def test_registration_is_not_deleted(self):
        player = Player.objects.create(nickname="Swettka")
        tm = self._make_message("рега 1 кланами", days_old=20, status=TelegramMessage.Status.PROCESSED)
        Registration.objects.create(
            player=player,
            telegram_message=tm,
            clans_count=1,
            payment_kk=Decimal("10.00"),
            description="",
            registered_at=timezone.now(),
        )
        call_command("cleanup_old_messages", days=14)
        self.assertEqual(TelegramMessage.objects.count(), 1)
