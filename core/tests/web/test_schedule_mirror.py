"""Tests for the Smartline web interface - ScheduleMirrorViewTests class."""

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



@override_settings(
    TELEGRAM_BOT_TOKEN="12345:TESTTOKEN",
    SCHEDULE_SOURCE_CHAT_ID=-5329088669,
    ALLIANCE_BOT_USERNAME="x5_fort_bot",
    CLAN_CHAT_ID=-1000000000,
)
class ScheduleMirrorViewTests(TestCase):
    def setUp(self):
        self.staff_user = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.non_staff_user = User.objects.create_user(
            username="player", password="test-password-123", is_staff=False
        )

    def _login_staff(self):
        self.client.login(username="kl", password="test-password-123")

    def _login_non_staff(self):
        self.client.login(username="player", password="test-password-123")

    def test_schedule_mirror_requires_login(self):
        """Non-staff users who are not Members are redirected to /login/."""
        self._login_non_staff()
        response = self.client.get(reverse("schedule_mirror"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_schedule_mirror_reconcile_action(self):
        """POST with action=reconcile calls reconcile_all and redirects."""
        self._login_staff()
        with mock.patch("core.views.schedule_mirror_service.reconcile_all") as mock_reconcile:
            response = self.client.post(
                reverse("schedule_mirror"),
                {"action": "reconcile"},
            )

            self.assertRedirects(response, reverse("schedule_mirror"))
            mock_reconcile.assert_called_once()

    def test_schedule_mirror_shows_current_active_mirror(self):
        """GET shows current active mirror text."""
        self._login_staff()
        ScheduleMirror.objects.create(
            source_chat_id=-5329088669,
            source_message_id=100,
            target_chat_id=-1000000000,
            target_message_id=999,
            last_text="Текущее расписание",
            is_active=True,
        )
        response = self.client.get(reverse("schedule_mirror"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Текущее расписание", content)
        self.assertNotIn("chat_id=-5329088669", content)
        self.assertNotIn("message_id=100", content)

    def test_admin_change_form_shows_schedule_source_info(self):
        from django.contrib.auth.models import User as AuthUser
        admin_user = AuthUser.objects.create_superuser(username="admin", password="admin-pass", email="a@example.com")
        self.client.login(username="admin", password="admin-pass")
        from core.models import ScheduleMirror
        mirror = ScheduleMirror.objects.create(
            source_chat_id=-5329088669,
            source_message_id=100,
            target_chat_id=-1000000000,
            target_message_id=999,
            alliance_bot_username="x5_fort_bot",
            last_text="Текущее расписание",
            is_active=True,
        )
        response = self.client.get(reverse("admin:core_schedulemirror_change", args=[mirror.pk]))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("chat_id=-5329088669", content)
        self.assertIn("message_id=100", content)
        self.assertIn("chat_id=-1000000000", content)
        self.assertIn("x5_fort_bot", content)


