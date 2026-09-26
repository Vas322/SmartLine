"""Tests for the standalone Epic Boss settings page /settings/epic-boss/."""
from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import BossRespawn
from core.services import boss_notification_service


class EpicBossSettingsWebTests(TestCase):
    """Standalone Epic RB settings page /settings/epic-boss/."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.non_staff = User.objects.create_user(
            username="nostaff", password="test-password-123", is_staff=False
        )
        now = timezone.now()
        self.antharas = BossRespawn.objects.create(
            boss_name="Antharas",
            boss_type=BossRespawn.BossType.EPIC,
            respawn_start=now,
            respawn_end=now + timedelta(hours=1),
        )

    def _login(self, user):
        self.client.login(username=user.username, password="test-password-123")

    def _settings(self):
        return boss_notification_service.get_settings()

    def test_settings_redirects_edit_epic_boss_get_to_epic_page(self):
        self._login(self.staff)
        response = self.client.get(reverse("settings") + "?edit_epic_boss=1")
        self.assertRedirects(
            response,
            reverse("settings_epic_boss") + "?edit=1",
            status_code=302,
            target_status_code=200,
        )

    def test_settings_redirects_epic_boss_post_to_epic_page(self):
        self._login(self.staff)
        response = self.client.post(
            reverse("settings"),
            {"save_epic_boss": "1", "is_enabled": "on"},
        )
        self.assertRedirects(response, reverse("settings_epic_boss"))

    def test_epic_boss_settings_page_loads(self):
        self._login(self.staff)
        response = self.client.get(reverse("settings_epic_boss"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Уведомления Эпик РБ", content)

    def test_epic_boss_view_mode(self):
        s = self._settings()
        s.is_enabled = True
        s.notification_time = time(18, 0)
        s.selected_bosses = ["Antharas"]
        s.save()

        self._login(self.staff)
        response = self.client.get(reverse("settings_epic_boss"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # Режим просмотра: нет полей формы, но есть кнопка редактирования.
        self.assertIn("Изменить настройку", content)
        self.assertNotIn('name="notification_time"', content)
        self.assertNotIn('name="save_epic_boss"', content)

    def test_epic_boss_edit_mode(self):
        s = self._settings()
        s.is_enabled = True
        s.save()

        self._login(self.staff)
        response = self.client.get(reverse("settings_epic_boss") + "?edit=1")
        content = response.content.decode()
        self.assertIn('name="notification_time"', content)
        self.assertIn('name="save_epic_boss" value="1"', content)
        self.assertIn("Отмена", content)

    def test_epic_boss_save_valid(self):
        self._login(self.staff)
        response = self.client.post(
            reverse("settings_epic_boss"),
            {
                "save_epic_boss": "1",
                "is_enabled": "on",
                "notification_time": "18:00",
                "topic": "",
                "bosses": ["Antharas"],
                "text_template": "🎮 Сегодня респ Эпик РБ\n\nБоссы:\n{bosses}",
            },
        )
        self.assertRedirects(response, reverse("settings_epic_boss"))
        s = self._settings()
        s.refresh_from_db()
        self.assertTrue(s.is_enabled)
        self.assertEqual(s.selected_bosses, ["Antharas"])

    def test_epic_boss_cancel_returns_to_view(self):
        s = self._settings()
        s.is_enabled = True
        s.save()

        self._login(self.staff)
        # В режиме редактирования кнопка «Отмена» ведёт на страницу без edit → режим просмотра.
        response = self.client.get(reverse("settings_epic_boss") + "?edit=1")
        content = response.content.decode()
        self.assertIn(f'href="{reverse("settings_epic_boss")}"', content)
        self.assertIn("Отмена", content)

        # Переход по «Отмена» возвращает в режим просмотра.
        follow = self.client.get(reverse("settings_epic_boss"))
        self.assertEqual(follow.status_code, 200)
        self.assertNotIn('name="notification_time"', follow.content.decode())

    def test_epic_boss_page_shows_disabled_hint_when_disabled(self):
        self._login(self.staff)
        response = self.client.get(reverse("settings_epic_boss"))
        content = response.content.decode()
        self.assertIn("Уведомления выключены", content)

    def test_settings_page_does_not_contain_epic_section(self):
        self._login(self.staff)
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertNotIn('name="notification_time"', content)
        self.assertNotIn('name="save_epic_boss"', content)
        self.assertNotIn('id="epic-boss"', content)

    def test_settings_epic_boss_tile_links_to_epic_page(self):
        self._login(self.staff)
        response = self.client.get(reverse("settings"))
        content = response.content.decode()
        self.assertIn(f'href="{reverse("settings_epic_boss")}"', content)

    def test_non_staff_cannot_access_settings_epic_boss(self):
        self._login(self.non_staff)
        response = self.client.get(reverse("settings_epic_boss"))
        self.assertEqual(response.status_code, 404)

    def test_non_staff_cannot_save_epic_boss(self):
        self._login(self.non_staff)
        response = self.client.post(
            reverse("settings_epic_boss"),
            {"save_epic_boss": "1", "is_enabled": "on"},
        )
        self.assertEqual(response.status_code, 404)
