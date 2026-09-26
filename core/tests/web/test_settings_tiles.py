"""Tests for the settings hub navigation tiles (anchor mode)."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import CastRate, Rate, RegistrationRate
from core.services import boss_notification_service, welcome_service


class SettingsTilesWebTests(TestCase):
    """Settings page: hub tiles with anchors and statuses."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.client.login(username="kl", password="test-password-123")

    def _reset(self):
        welcome_settings = welcome_service.get_welcome_settings()
        welcome_settings.welcome_text = ""
        welcome_settings.save()
        epic = boss_notification_service.get_settings()
        epic.is_enabled = False
        epic.save()
        # Убираем сид-тарифы из миграций (они активны по умолчанию).
        Rate.objects.all().delete()
        CastRate.objects.all().delete()
        RegistrationRate.objects.all().delete()

    def _get(self):
        return self.client.get(reverse("settings")).content.decode()

    def test_settings_page_contains_hub_nav_with_five_tiles(self):
        self._reset()
        content = self._get()
        self.assertIn('class="settings-tiles"', content)
        # Пять плиток-ссылок.
        self.assertEqual(content.count('class="settings-tile stat-card stat-card--gold"'), 5)

    def test_tiles_have_correct_links(self):
        self._reset()
        content = self._get()
        # Тарифы за DEF ведут на отдельную страницу тарифов, welcome — на /settings/welcome/,
        # epic — на /settings/epic-boss/, остальные — на settings.
        self.assertIn(f'href="{reverse("rates")}"', content)
        self.assertIn(f'href="{reverse("settings")}"', content)
        self.assertIn(f'href="{reverse("settings_welcome")}"', content)
        self.assertIn(f'href="{reverse("settings_epic_boss")}"', content)

    def test_tile_titles_present(self):
        self._reset()
        content = self._get()
        for title in (
            "Тарифы за DEF",
            "Тарифы за каст",
            "Тарифы за регистрацию",
            "Приветствие",
            "Уведомления Эпик РБ",
        ):
            self.assertIn(title, content)

    def test_status_off_when_all_settings_disabled(self):
        self._reset()
        content = self._get()
        # Все статусы «Выключено» / 0 активных тарифов.
        self.assertIn("0 активных тарифов", content)
        self.assertIn("status--off", content)
        self.assertNotIn("status--on", content)

    def test_status_on_for_active_rates(self):
        # Убираем сид-тарифы из миграций, чтобы считать только созданные.
        Rate.objects.all().delete()
        CastRate.objects.all().delete()
        RegistrationRate.objects.all().delete()
        Rate.objects.create(start_time="00:00", end_time="08:00", rate_kk=Decimal("100"), active=True)
        CastRate.objects.create(start_time="00:00", end_time="08:00", rate_kk=Decimal("50"), active=True)
        RegistrationRate.objects.create(start_time="00:00", end_time="23:59", rate_kk=Decimal("10"), active=True)
        content = self._get()
        self.assertIn("1 активных тарифов", content)

    def test_status_on_for_welcome(self):
        settings = welcome_service.get_welcome_settings()
        settings.welcome_text = "Добро пожаловать!"
        settings.save()
        content = self._get()
        self.assertIn("Включено", content)

    def test_status_on_for_epic_boss(self):
        settings = boss_notification_service.get_settings()
        settings.is_enabled = True
        settings.notification_time = "18:00"
        settings.save()
        content = self._get()
        self.assertIn("Включено · 18:00 МСК", content)

    def test_settings_page_does_not_contain_rate_forms(self):
        """Rate forms are only on /settings/rates/, not on /settings/."""
        content = self._get()
        # Settings page should NOT have rate table form controls
        # (no start_time/end_time/rate_kk inputs, no rate action buttons)
        self.assertNotIn('name="add_rate"', content)
        self.assertNotIn('name="add_cast_rate"', content)
        self.assertNotIn('name="add_reg_rate"', content)
        # But welcome/epic sections are still there
        self.assertIn("Приветствие", content)
        self.assertIn("Уведомления Эпик РБ", content)
