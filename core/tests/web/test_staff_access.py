"""Tests for the Smartline web interface - StaffAccessTests class."""

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
class StaffAccessTests(TestCase):
    """Tests for hiding staff pages from non-staff Members."""

    def setUp(self):
        self.member_user = User.objects.create_user(
            username="member", password="test-password-123", is_staff=False
        )
        members_group, _ = Group.objects.get_or_create(name="Members")
        self.member_user.groups.add(members_group)
        self.staff_user = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.instruction = Instruction.objects.create(
            slug="how-to", title="Инструкция", content="Текст"
        )
        self.player = Player.objects.create(nickname="Swettka")
        self.message = TelegramMessage.objects.create(
            telegram_chat_id=11,
            telegram_message_id=21,
            telegram_user_id=101,
            telegram_username="swettka",
            text="+1 | деф | Swettka | Первая волна",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        self.activity = Activity.objects.create(
            player=self.player,
            telegram_message=self.message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            description="Первая волна",
        )

    def _login_member(self):
        self.client.login(username="member", password="test-password-123")

    def _login_staff(self):
        self.client.login(username="kl", password="test-password-123")

    def test_member_nav_hides_staff_links(self):
        """Member header shows Dashboard/Instructions/Schedule, not staff links."""
        self._login_member()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("players"))
        self.assertNotContains(response, reverse("activities"))
        self.assertNotContains(response, reverse("telegram_messages"))
        self.assertNotContains(response, reverse("settings"))
        self.assertContains(response, reverse("instructions"))
        self.assertContains(response, reverse("schedule_mirror"))

    def test_staff_nav_shows_all_links(self):
        """Staff header shows all links including staff pages."""
        self._login_staff()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("players"))
        self.assertContains(response, reverse("activities"))
        self.assertContains(response, reverse("telegram_messages"))
        self.assertContains(response, reverse("settings"))

    def test_member_direct_access_to_staff_pages_returns_404(self):
        """Non-staff Members get 404 when hitting staff URLs directly."""
        self._login_member()
        for url_name, kwargs in [
            ("players", {}),
            ("activities", {}),
            ("telegram_messages", {}),
            ("settings", {}),
            ("instruction_edit", {"pk": self.instruction.pk}),
            ("player_detail", {"pk": self.player.pk}),
            ("player_edit", {"pk": self.player.pk}),
        ]:
            response = self.client.get(reverse(url_name, kwargs=kwargs))
            self.assertEqual(response.status_code, 404, url_name)

        # toggle/delete require POST; staff_or_404 still blocks non-staff first.
        for url_name in ["player_toggle", "player_delete"]:
            response = self.client.post(
                reverse(url_name, kwargs={"pk": self.player.pk})
            )
            self.assertEqual(response.status_code, 404, url_name)

    def test_member_schedule_mirror_returns_200(self):
        """Members can read the schedule (GET returns 200)."""
        self._login_member()
        response = self.client.get(reverse("schedule_mirror"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Синхронизировать сейчас")

    def test_member_schedule_mirror_reconcile_returns_403(self):
        """Members cannot trigger a reconcile (POST returns 403)."""
        self._login_member()
        response = self.client.post(
            reverse("schedule_mirror"), {"action": "reconcile"}
        )
        self.assertEqual(response.status_code, 403)

    def test_member_instructions_page_hides_add_and_delete(self):
        """Member instructions page hides add/delete buttons but keeps detail links."""
        self._login_member()
        response = self.client.get(reverse("instructions"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn("Добавить инструкцию", content)
        self.assertNotIn("Удалить", content)
        self.assertIn(
            reverse("instruction_detail", args=[self.instruction.pk]), content
        )

    def test_staff_instructions_page_shows_add_and_delete(self):
        """Staff instructions page shows add/delete buttons."""
        self._login_staff()
        response = self.client.get(reverse("instructions"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Добавить инструкцию", content)
        self.assertIn("Удалить", content)

    def test_member_instructions_add_post_forbidden(self):
        """Member cannot add an instruction (POST returns 403)."""
        self._login_member()
        response = self.client.post(
            reverse("instructions"), {"action": "add"}
        )
        self.assertEqual(response.status_code, 403)

    def test_member_instructions_delete_post_forbidden(self):
        """Member cannot delete an instruction (POST returns 403)."""
        self._login_member()
        response = self.client.post(
            reverse("instructions"),
            {"action": "delete", "pk": self.instruction.pk},
        )
        self.assertEqual(response.status_code, 403)

    def test_staff_instructions_add_post_ok(self):
        """Staff can add an instruction (POST redirects)."""
        self._login_staff()
        count_before = Instruction.objects.count()
        response = self.client.post(
            reverse("instructions"), {"action": "add"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Instruction.objects.count(), count_before + 1)

    def test_member_dashboard_nick_not_linked(self):
        """Member dashboard nick is plain text (no player profile link)."""
        self._login_member()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("/player/", response.content.decode())

    def test_staff_dashboard_nick_linked(self):
        """Staff dashboard nick links to the player profile."""
        self._login_staff()
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("/player/", response.content.decode())


