"""Tests for the summoner bonus section of the web interface."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.services import summoner_bonus_service


class SummonerBonusSettingsWebTests(TestCase):
    """Settings page: summoner bonus section (view mode + edit mode)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.non_staff = User.objects.create_user(
            username="nostaff", password="test-password-123", is_staff=False
        )

    def _login(self, user):
        self.client.login(username=user.username, password="test-password-123")

    def _reset(self):
        settings = summoner_bonus_service.get_settings()
        settings.is_enabled = False
        settings.percent = Decimal("0.5")
        settings.save()

    def test_settings_page_contains_summoner_bonus_section(self):
        self._reset()
        self._login(self.staff)
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Надбавка за суммонеров", content)
        self.assertIn("Изменить", content)
        # Режим просмотра по умолчанию: значения видны, форма НЕ видна.
        self.assertNotIn('name="is_enabled"', content)
        self.assertNotIn('name="percent"', content)
        self.assertNotIn('name="save_summoner_bonus"', content)

    def test_view_mode_shows_current_values(self):
        settings = summoner_bonus_service.get_settings()
        settings.is_enabled = True
        settings.percent = Decimal("3.5")
        settings.save()

        self._login(self.staff)
        response = self.client.get(reverse("settings"))
        content = response.content.decode()
        self.assertIn("Надбавка за суммонеров: Включена", content)
        self.assertIn("% за 1 суммонера: 3,50%", content)

    def test_view_mode_shows_disabled_value(self):
        self._reset()
        self._login(self.staff)
        response = self.client.get(reverse("settings"))
        content = response.content.decode()
        self.assertIn("Надбавка за суммонеров: Выключена", content)

    def test_edit_param_opens_form(self):
        self._reset()
        self._login(self.staff)
        response = self.client.get(reverse("rates") + "?tab=summoner&edit_summoner_bonus=1")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Форма редактирования открыта.
        self.assertIn('name="is_enabled"', content)
        self.assertIn('name="percent"', content)
        self.assertIn('name="save_summoner_bonus" value="1"', content)
        self.assertIn("Отмена", content)

    def test_edit_mode_prefills_current_values(self):
        settings = summoner_bonus_service.get_settings()
        settings.is_enabled = True
        settings.percent = Decimal("3.5")
        settings.save()

        self._login(self.staff)
        response = self.client.get(reverse("rates") + "?tab=summoner&edit_summoner_bonus=1")
        content = response.content.decode()
        # Чекбокс отмечен при включённой надбавке.
        self.assertRegex(content, r'name="is_enabled"[^>]*checked')
        self.assertIn('name="percent" value="3.50"', content)

    def test_save_enabled_and_percent(self):
        self._reset()
        self._login(self.staff)
        response = self.client.post(
            reverse("rates"),
            {
                "save_summoner_bonus": "1",
                "is_enabled": "on",
                "percent": "3.5",
            },
        )
        self.assertRedirects(response, reverse("rates"))
        settings = summoner_bonus_service.get_settings()
        settings.refresh_from_db()
        self.assertTrue(settings.is_enabled)
        self.assertEqual(settings.percent, Decimal("3.5"))
        # После сохранения — снова режим просмотра с новыми значениями.
        response = self.client.get(reverse("settings"))
        content = response.content.decode()
        self.assertIn("Надбавка за суммонеров: Включена", content)
        self.assertIn("% за 1 суммонера: 3,50%", content)
        self.assertNotIn('name="save_summoner_bonus"', content)

    def test_save_disabled_and_percent(self):
        # Изначально включаем, потом выключаем чекбокс.
        settings = summoner_bonus_service.get_settings()
        settings.is_enabled = True
        settings.percent = Decimal("3.5")
        settings.save()

        self._login(self.staff)
        response = self.client.post(
            reverse("rates"),
            {
                "save_summoner_bonus": "1",
                "percent": "2.0",
            },
        )
        self.assertRedirects(response, reverse("rates"))
        settings.refresh_from_db()
        self.assertFalse(settings.is_enabled)
        self.assertEqual(settings.percent, Decimal("2.0"))
        # После сохранения — снова режим просмотра с новыми значениями.
        response = self.client.get(reverse("settings"))
        content = response.content.decode()
        self.assertIn("Надбавка за суммонеров: Выключена", content)
        self.assertIn("% за 1 суммонера: 2,00%", content)

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

    def test_edit_mode_has_active_enabled_at_input(self):
        self._reset()
        self._login(self.staff)
        response = self.client.get(reverse("rates") + "?tab=summoner&edit_summoner_bonus=1")
        content = response.content.decode()
        # Поле даты включения — активный input типа datetime-local (не disabled).
        self.assertIn('name="enabled_at_display"', content)
        self.assertIn('type="datetime-local"', content)
        self.assertNotIn('name="enabled_at_display" disabled', content)

    def test_save_with_explicit_enabled_at(self):
        from datetime import datetime, timedelta

        from django.utils import timezone

        self._reset()
        self._login(self.staff)
        custom = timezone.localtime() + timedelta(days=1)
        response = self.client.post(
            reverse("rates"),
            {
                "save_summoner_bonus": "1",
                "is_enabled": "on",
                "percent": "3.5",
                "enabled_at_display": custom.strftime("%d.%m.%Y %H:%M"),
            },
        )
        self.assertRedirects(response, reverse("rates"))
        settings = summoner_bonus_service.get_settings()
        settings.refresh_from_db()
        self.assertTrue(settings.is_enabled)
        self.assertIsNotNone(settings.enabled_at)
        expected = timezone.make_aware(
            datetime(
                custom.year,
                custom.month,
                custom.day,
                custom.hour,
                custom.minute,
            ),
            timezone.get_current_timezone(),
        )
        self.assertEqual(settings.enabled_at, expected)

    def test_save_with_empty_enabled_at_sets_now(self):
        from django.utils import timezone

        self._reset()
        settings = summoner_bonus_service.get_settings()
        settings.enabled_at = None
        settings.save()

        before = timezone.now()
        self._login(self.staff)
        response = self.client.post(
            reverse("rates"),
            {
                "save_summoner_bonus": "1",
                "is_enabled": "on",
                "percent": "3.5",
                "enabled_at_display": "",
            },
        )
        self.assertRedirects(response, reverse("rates"))
        settings.refresh_from_db()
        self.assertTrue(settings.is_enabled)
        self.assertIsNotNone(settings.enabled_at)
        self.assertGreaterEqual(settings.enabled_at, before)

    def test_save_with_invalid_enabled_at_keeps_form_open(self):
        self._reset()
        self._login(self.staff)
        response = self.client.post(
            reverse("rates"),
            {
                "save_summoner_bonus": "1",
                "is_enabled": "on",
                "percent": "3.5",
                "enabled_at_display": "не-дата",
            },
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Форма остаётся открытой с ошибкой валидации.
        self.assertIn('name="save_summoner_bonus" value="1"', content)
        self.assertIn("error", content)
