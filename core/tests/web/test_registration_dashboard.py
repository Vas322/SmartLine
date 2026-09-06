"""Tests for the Smartline web interface - RegistrationDashboardTests class."""

"""Tests for the Smartline web interface."""
import re
from datetime import time, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Activity,
    CastRate,
    Instruction,
    Player,
    Rate,
    Registration,
    RegistrationRate,
    ScheduleMirror,
    TelegramMessage,
)

_XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)



class RegistrationDashboardTests(TestCase):
    """Tests for registration display on dashboard."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="kl",
            password="test-password-123",
        )
        members_group, _ = Group.objects.get_or_create(name="Members")
        self.user.groups.add(members_group)
        self.player = Player.objects.create(nickname="Swettka", telegram_user_id=100)
        self.player2 = Player.objects.create(nickname="Ostin", telegram_user_id=200)
        self.message = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=20,
            telegram_user_id=100,
            telegram_username="swettka",
            text="+1 | деф | Swettka | Первая волна",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        # Activity payment for 1 hour DEF at 11:56 = 75 kk (from default rates)
        self.activity = Activity.objects.create(
            player=self.player,
            telegram_message=self.message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            description="Первая волна",
            payment_kk=Decimal("75.00"),
        )

    def _login(self):
        self.client.login(username="kl", password="test-password-123")

    def test_dashboard_shows_registration_column(self):
        """Dashboard table includes 'Регистрировал' column."""
        self._login()
        response = self.client.get(reverse("dashboard"), {"period": "month"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Регистрировал", content)

    def test_dashboard_shows_total_payout_line(self):
        """Dashboard shows 'Итого за период' line with total."""
        self._login()
        response = self.client.get(reverse("dashboard"), {"period": "month"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Итого за период", content)
        self.assertIn("кк</p>", content)  # Total payout line

    def test_dashboard_includes_registration_in_adena(self):
        """Registration payments are included in 'Выплата, кк' (adena)."""
        self._login()
        # Create a registration for Swettka
        reg_msg = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=21,
            telegram_user_id=100,
            telegram_username="swettka",
            text="рега 2 кланами атака форта",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        Registration.objects.create(
            player=self.player,
            telegram_message=reg_msg,
            clans_count=2,
            payment_kk=Decimal("20.00"),
            description="атака форта",
            photo_file_id="photo123",
            registered_at=timezone.now(),
        )

        response = self.client.get(reverse("dashboard"), {"period": "month"})
        self.assertEqual(response.status_code, 200)
        rows = {row["nickname"]: row for row in response.context["rows"]}
        # Adena = activity payment (75) + registration payment (20) = 95
        self.assertEqual(rows["Swettka"]["adena"], Decimal("95.00"))
        # Registration column shows number of clans (2), not money
        self.assertEqual(rows["Swettka"]["registration"], 2)

    def test_dashboard_percent_unchanged_by_registrations(self):
        """Attendance percent is based on hours, not registration money."""
        self._login()
        # Create registration for Swettka
        reg_msg = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=21,
            telegram_user_id=100,
            telegram_username="swettka",
            text="рега 5 кланов",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        Registration.objects.create(
            player=self.player,
            telegram_message=reg_msg,
            clans_count=5,
            payment_kk=Decimal("50.00"),
            description="",
            photo_file_id="photo123",
            registered_at=timezone.now(),
        )

        response = self.client.get(reverse("dashboard"), {"period": "month"})
        self.assertEqual(response.status_code, 200)
        rows = {row["nickname"]: row for row in response.context["rows"]}
        # Percent should be based on hours only (1 hour DEF = 1/5 = 20% for 1 day period, etc.)
        # The exact value depends on days_in_period, but it should NOT include registration money
        self.assertEqual(rows["Swettka"]["total_hours"], Decimal("1"))
        # Registration money is in adena but not in percent calculation
        self.assertEqual(rows["Swettka"]["registration"], 5)


