"""Tests for the settings hub navigation tiles (anchor mode)."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import CastRate, Rate, RegistrationRate
from core.services import boss_notification_service, summoner_bonus_service, welcome_service


class SettingsTilesWebTests(TestCase):
    """Settings page: hub tiles with anchors and statuses."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.client.login(username="kl", password="test-password-123")

    def _reset(self):
        summoner = summoner_bonus_service.get_settings()
        summoner.is_enabled = False
        summoner.percent = Decimal("0.5")
        summoner.save()
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

    def test_settings_page_contains_hub_nav_with_six_tiles(self):
        self._reset()
        content = self._get()
        self.assertIn('class="settings-tiles"', content)
        # Шесть плиток-ссылок.
        self.assertEqual(content.count('class="settings-tile stat-card stat-card--gold"'), 6)

    def test_tiles_have_correct_anchors(self):
        self._reset()
        content = self._get()
        for anchor in ("rates-def", "rates-cast", "rates-reg", "summoner", "welcome", "epic-boss"):
            self.assertIn(f'href="#{anchor}"', content)
        # У каждой карточки-секции есть свой id.
        for anchor in ("rates-def", "rates-cast", "rates-reg", "summoner", "welcome", "epic-boss"):
            self.assertIn(f'id="{anchor}"', content)

    def test_tile_titles_present(self):
        self._reset()
        content = self._get()
        for title in (
            "Тарифы за DEF",
            "Тарифы за каст",
            "Тарифы за регистрацию",
            "Надбавка за суммонеров",
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

    def test_status_on_for_summoner(self):
        settings = summoner_bonus_service.get_settings()
        settings.is_enabled = True
        settings.percent = Decimal("3.5")
        settings.save()
        content = self._get()
        self.assertIn("Включено · 3,50% за суммонера", content)
        self.assertIn("status--on", content)

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
