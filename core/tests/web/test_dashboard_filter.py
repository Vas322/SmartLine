"""Tests for the Smartline web interface - DashboardFilterZeroActivityTests class."""
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



class DashboardFilterZeroActivityTests(TestCase):
    """Tests for hiding zero-activity players on the dashboard."""

    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )

    def _login(self):
        self.client.login(username="kl", password="test-password-123")

    def _make_message(self, chat_id, msg_id, user_id):
        return TelegramMessage.objects.create(
            telegram_chat_id=chat_id,
            telegram_message_id=msg_id,
            telegram_user_id=user_id,
            telegram_username="test",
            text="+1 | деф | Test | Волна",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )

    def test_dashboard_hides_zero_activity_player(self):
        """Player without activity does not appear on the dashboard."""
        Player.objects.create(nickname="Нульник")
        self._login()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("Нульник", content)

    def test_dashboard_shows_def_activity_player(self):
        """Player with DEF activity appears and shows def hours."""
        player = Player.objects.create(nickname="Дефщик")
        msg = self._make_message(100, 200, 300)
        Activity.objects.create(
            player=player,
            telegram_message=msg,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            description="Оборона",
        )
        self._login()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Дефщик", content)
        self.assertIn("1", content)

    def test_dashboard_shows_farm_activity_player(self):
        """Player with FARM activity appears on the dashboard."""
        player = Player.objects.create(nickname="Фармер")
        msg = self._make_message(101, 201, 301)
        Activity.objects.create(
            player=player,
            telegram_message=msg,
            amount=Decimal("2"),
            activity_type=Activity.ActivityType.FARM,
            description="Фарм",
        )
        self._login()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Фармер", content)

    def test_dashboard_shows_cast_activity_player(self):
        """Player with CAST activity (has_cast=True) appears on the dashboard."""
        player = Player.objects.create(nickname="Кастер")
        msg = self._make_message(102, 202, 302)
        Activity.objects.create(
            player=player,
            telegram_message=msg,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.CAST,
            has_cast=True,
            description="Кастует",
        )
        self._login()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Кастер", content)

    def test_dashboard_shows_registration_only_player(self):
        """Player with only registration (no activity) appears on the dashboard."""
        player = Player.objects.create(nickname="Резервист")
        msg = self._make_message(103, 203, 303)
        Registration.objects.create(
            player=player,
            telegram_message=msg,
            clans_count=1,
            payment_kk=Decimal("100.00"),
            registered_at=timezone.now(),
        )
        self._login()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Резервист", content)
        self.assertIn("1", content)  # clans_count=1

    def test_dashboard_total_payout_unaffected_by_filter(self):
        """Total payout shown on dashboard covers all activities regardless of filter."""
        # Player with activity
        player_active = Player.objects.create(nickname="АктивныйИгрок")
        msg1 = self._make_message(110, 210, 310)
        Activity.objects.create(
            player=player_active,
            telegram_message=msg1,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            payment_kk=Decimal("75.00"),
            description="Волна",
        )
        # Player without any activity — should not appear but payout must not be affected
        Player.objects.create(nickname="ПассивныйИгрок")
        self._login()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("АктивныйИгрок", content)
        self.assertNotIn("ПассивныйИгрок", content)
        self.assertIn("Итого за период", content)
        # Filter (hiding zero-activity players) must not affect total payout:
        # 75 from the active player; passive player contributes 0.
        # Note: Django renders Decimal("75.00") as "75" (no decimal part).
        self.assertRegex(content, r"Итого за период:\s*75\s*кк")


