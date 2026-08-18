"""Tests for the clear_data management command."""
from datetime import time
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from core.models import (
    Activity,
    Instruction,
    Player,
    ProcessingError,
    Rate,
    TelegramMessage,
)


class ClearDataCommandTests(TestCase):
    def setUp(self):
        self.player = Player.objects.create(nickname="Swettka")
        self.message = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=20,
            telegram_user_id=100,
            telegram_username="swettka",
            text="x",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        self.activity = Activity.objects.create(
            player=self.player,
            telegram_message=self.message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            description="",
        )
        self.error = ProcessingError.objects.create(
            telegram_message=self.message,
            reason="x",
        )
        self.instruction = Instruction.objects.create(
            slug="keep",
            title="Keep",
            content="x",
        )
        self.rate = Rate.objects.create(
            start_time=time(0, 1),
            end_time=time(8, 0),
            rate_kk=Decimal("100"),
        )

    def test_clear_data(self):
        call_command("clear_data")

        self.assertEqual(Player.objects.count(), 0)
        self.assertEqual(Activity.objects.count(), 0)
        self.assertEqual(TelegramMessage.objects.count(), 0)
        self.assertEqual(ProcessingError.objects.count(), 0)

        self.assertGreaterEqual(Instruction.objects.count(), 1)
        self.assertGreaterEqual(Rate.objects.count(), 1)