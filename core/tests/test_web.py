"""Tests for the Smartline web interface."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Activity, Player, TelegramMessage

_XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


class WebInterfaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="kl",
            password="test-password-123",
        )
        self.player = Player.objects.create(nickname="Swettka")
        self.message = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=20,
            telegram_user_id=100,
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

    def _login(self):
        self.client.login(username="kl", password="test-password-123")

    def test_pages_redirect_anonymous_to_login(self):
        for url_name in ["dashboard", "players", "activities", "telegram_messages", "processing_errors", "settings"]:
            response = self.client.get(reverse(url_name))
            self.assertRedirects(
                response,
                f"{reverse('login')}?next={reverse(url_name)}",
            )

    def test_login_page_available(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

    def test_pages_available_after_login(self):
        self._login()
        for url_name in ["dashboard", "players", "activities", "telegram_messages", "processing_errors", "settings"]:
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 200, url_name)

    def test_period_filter_works(self):
        self._login()
        old_activity = Activity.objects.create(
            player=self.player,
            telegram_message=TelegramMessage.objects.create(
                telegram_chat_id=10,
                telegram_message_id=99,
                text="+1 | деф | Swettka | старая",
                message_date=timezone.now(),
                status=TelegramMessage.Status.PROCESSED,
            ),
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            description="старая",
        )
        Activity.objects.filter(pk=old_activity.pk).update(
            created_at=timezone.now() - timedelta(days=45)
        )

        response = self.client.get(reverse("dashboard"), {"period": "today"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Swettka", content)
        # only today's activity counted: def hours column shows 1, not 2
        self.assertIn("<td>1</td>", content)
        self.assertNotIn("<td>2</td>", content)

    def test_player_detail_page_available_after_login(self):
        self._login()
        response = self.client.get(
            reverse("player_detail", args=[self.player.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("По дням", response.content.decode())

    def test_dashboard_shows_percent_and_columns(self):
        self._login()
        response = self.client.get(reverse("dashboard"), {"period": "month"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        for text in ["Ник", "Адена", "Дефал", "Фармил", "%"]:
            self.assertIn(text, content)

    def test_excel_export_returns_xlsx_after_login(self):
        self._login()
        response = self.client.get(reverse("export_excel"), {"period": "today"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], _XLSX_CONTENT_TYPE)
        self.assertGreater(len(response.content), 0)

    def test_excel_export_requires_login(self):
        response = self.client.get(reverse("export_excel"), {"period": "today"})
        self.assertEqual(response.status_code, 302)

    def test_player_creation_and_toggle(self):
        self._login()
        response = self.client.post(reverse("players"), {"nickname": "Ostin"})
        self.assertRedirects(response, reverse("players"))
        player = Player.objects.get(nickname="Ostin")
        self.assertTrue(player.is_active)

        response = self.client.post(reverse("player_toggle", args=[player.pk]))
        self.assertRedirects(response, reverse("players"))
        player.refresh_from_db()
        self.assertFalse(player.is_active)

    def test_player_toggle_get_returns_405_and_does_not_change_state(self):
        self._login()
        player = self.player
        self.assertTrue(player.is_active)

        response = self.client.get(reverse("player_toggle", args=[player.pk]))

        self.assertEqual(response.status_code, 405)
        player.refresh_from_db()
        self.assertTrue(player.is_active)
