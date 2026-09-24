"""Tests for the summoner bonus section of the web interface."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.services import summoner_bonus_service


class SummonerBonusSettingsWebTests(TestCase):
    """Settings page: summoner bonus section (save checkbox and percent)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.non_staff = User.objects.create_user(
            username="nostaff", password="test-password-123", is_staff=False
        )

    def _login(self, user):
        self.client.login(username=user.username, password="test-password-123")

    def test_settings_page_contains_summoner_bonus_section(self):
        self._login(self.staff)
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Надбавка за суммонеров", content)
        self.assertIn('name="is_enabled"', content)
        self.assertIn('name="percent"', content)
        self.assertIn('name="save_summoner_bonus"', content)
        self.assertIn('name="save_summoner_bonus" value="1"', content)

    def test_settings_page_prefills_current_values(self):
        settings = summoner_bonus_service.get_settings()
        settings.is_enabled = True
        settings.percent = Decimal("3.5")
        settings.save()

        self._login(self.staff)
        response = self.client.get(reverse("settings"))
        content = response.content.decode()
        # Чекбокс отмечен при включённой надбавке.
        self.assertRegex(content, r'name="is_enabled"[^>]*checked')
        self.assertIn('name="percent" value="3.50"', content)

    def test_save_enabled_and_percent(self):
        self._login(self.staff)
        response = self.client.post(
            reverse("settings"),
            {
                "save_summoner_bonus": "1",
                "is_enabled": "on",
                "percent": "3.5",
            },
        )
        self.assertRedirects(response, reverse("settings"))
        settings = summoner_bonus_service.get_settings()
        settings.refresh_from_db()
        self.assertTrue(settings.is_enabled)
        self.assertEqual(settings.percent, Decimal("3.5"))

    def test_save_disabled_and_percent(self):
        # Изначально включаем, потом выключаем чекбокс.
        settings = summoner_bonus_service.get_settings()
        settings.is_enabled = True
        settings.percent = Decimal("3.5")
        settings.save()

        self._login(self.staff)
        response = self.client.post(
            reverse("settings"),
            {
                "save_summoner_bonus": "1",
                "percent": "2.0",
            },
        )
        self.assertRedirects(response, reverse("settings"))
        settings.refresh_from_db()
        self.assertFalse(settings.is_enabled)
        self.assertEqual(settings.percent, Decimal("2.0"))

    def test_non_staff_cannot_access_settings(self):
        self._login(self.non_staff)
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 404)

    def test_non_staff_cannot_save_summoner_bonus(self):
        self._login(self.non_staff)
        response = self.client.post(
            reverse("settings"),
            {"save_summoner_bonus": "1", "is_enabled": "on", "percent": "5"},
        )
        self.assertEqual(response.status_code, 404)
