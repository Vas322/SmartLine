"""Tests for the welcome section of the web interface."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import Player
from core.services import welcome_service


class WelcomeSettingsWebTests(TestCase):
    """Settings page: welcome section (text save / block reset / access)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.non_staff = User.objects.create_user(
            username="nostaff", password="test-password-123", is_staff=False
        )

    def _login(self, user):
        self.client.login(username=user.username, password="test-password-123")

    def test_settings_page_contains_welcome_section(self):
        self._login(self.staff)
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Приветствие", content)
        self.assertIn('name="welcome_text"', content)
        self.assertIn('name="save_welcome"', content)
        self.assertIn('name="save_welcome" value="1"', content)

    def test_settings_page_shows_disabled_hint_when_text_empty(self):
        self._login(self.staff)
        response = self.client.get(reverse("settings"))
        content = response.content.decode()
        self.assertIn("Приветствия выключены (текст пуст)", content)

    def test_settings_page_shows_welcome_preview_when_text_saved(self):
        settings = welcome_service.get_welcome_settings()
        settings.welcome_text = "Добро пожаловать в клан!"
        settings.save()

        self._login(self.staff)
        response = self.client.get(reverse("settings"))
        content = response.content.decode()
        self.assertIn("Текущее приветствие", content)
        self.assertIn("Добро пожаловать в клан!", content)
        self.assertIn("?edit_welcome=1", content)
        self.assertNotIn('name="welcome_text"', content)

    def test_settings_page_opens_welcome_edit_with_edit_welcome_param(self):
        settings = welcome_service.get_welcome_settings()
        settings.welcome_text = "Добро пожаловать в клан!"
        settings.save()

        self._login(self.staff)
        response = self.client.get(reverse("settings") + "?edit_welcome=1")
        content = response.content.decode()
        self.assertIn('name="welcome_text"', content)
        self.assertIn('name="save_welcome" value="1"', content)
        self.assertIn("Отмена", content)

    def test_settings_save_welcome_text(self):
        self._login(self.staff)
        response = self.client.post(
            reverse("settings"),
            {"save_welcome": "1", "welcome_text": "Добро пожаловать в клан!"},
        )
        self.assertRedirects(response, reverse("settings"))
        settings = welcome_service.get_welcome_settings()
        settings.refresh_from_db()
        self.assertEqual(settings.welcome_text, "Добро пожаловать в клан!")

    def test_settings_reset_welcome_block(self):
        settings = welcome_service.get_welcome_settings()
        settings.block_until = timezone.now() + timedelta(minutes=30)
        settings.save()

        self._login(self.staff)
        response = self.client.post(
            reverse("settings"),
            {"reset_welcome_block": "1"},
        )
        self.assertRedirects(response, reverse("settings"))
        settings.refresh_from_db()
        self.assertIsNone(settings.block_until)

    def test_settings_page_shows_blocked_message_when_blocked(self):
        settings = welcome_service.get_welcome_settings()
        settings.block_until = timezone.now() + timedelta(minutes=30)
        settings.save()

        self._login(self.staff)
        response = self.client.get(reverse("settings"))
        content = response.content.decode()
        self.assertIn("Приветствия временно отключены из-за массового захода", content)
        self.assertIn('name="reset_welcome_block"', content)
        self.assertIn('name="reset_welcome_block" value="1"', content)

    def test_non_staff_cannot_access_settings(self):
        self._login(self.non_staff)
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 404)

    def test_non_staff_cannot_save_welcome(self):
        self._login(self.non_staff)
        response = self.client.post(
            reverse("settings"),
            {"save_welcome": "1", "welcome_text": "Хак"},
        )
        self.assertEqual(response.status_code, 404)


class PlayersPageWelcomeTests(TestCase):
    """Players page: nickname dash, Telegram nickname column, header rename."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.client.login(username="kl", password="test-password-123")

    def test_players_page_shows_dash_for_empty_nickname_and_telegram_nick(self):
        Player.objects.create(
            nickname=None,
            telegram_user_id=111,
            telegram_username="newbie",
            is_active=True,
        )
        response = self.client.get(reverse("players"))
        content = response.content.decode()
        self.assertIn("Принят в клан", content)  # переименованный заголовок
        self.assertIn("Ник в Telegram", content)
        self.assertIn("newbie", content)
        # прочерк для пустого ника
        self.assertRegex(content, r"<td>—</td>")

    def test_players_page_keeps_real_nickname(self):
        Player.objects.create(nickname="Swettka", is_active=True)
        response = self.client.get(reverse("players"))
        content = response.content.decode()
        self.assertIn("Swettka", content)
