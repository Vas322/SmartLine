"""Tests for the Epic Boss notifications settings block (view + edit modes)."""
from datetime import time, timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import BossRespawn
from core.services import boss_notification_service


class EpicBossNotificationSettingsViewTests(TestCase):
    """Settings block «Уведомления Эпик РБ» — read-only by default, edit on demand."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="kl",
            password="test-password-123",
            is_staff=True,
        )
        self.client.login(username="kl", password="test-password-123")

        now = timezone.now()
        self.antharas = BossRespawn.objects.create(
            boss_name="Antharas",
            boss_type=BossRespawn.BossType.EPIC,
            respawn_start=now,
            respawn_end=now + timedelta(hours=1),
        )
        self.valakas = BossRespawn.objects.create(
            boss_name="Valakas",
            boss_type=BossRespawn.BossType.EPIC,
            respawn_start=now + timedelta(hours=2),
            respawn_end=now + timedelta(hours=3),
        )
        self.kernon = BossRespawn.objects.create(
            boss_name="Kernon",
            boss_type=BossRespawn.BossType.SUBCLASS,
            respawn_start=now + timedelta(hours=4),
            respawn_end=now + timedelta(hours=5),
        )

    def _settings(self):
        return boss_notification_service.get_settings()

    def test_view_mode_hides_form_and_shows_current_values(self):
        s = self._settings()
        s.is_enabled = True
        s.notification_time = time(18, 0)
        s.selected_bosses = ["Antharas", "Valakas"]
        s.save()

        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        # Нет инпутов формы в режиме просмотра.
        self.assertNotIn('name="notification_time"', content)
        # Есть кнопка перехода в режим редактирования и текущие значения.
        self.assertIn("Изменить настройку", content)
        self.assertIn("включены", content)
        self.assertIn("18:00", content)
        # Перечень выбранных боссов.
        self.assertIn("Antharas, Valakas", content)

    def test_view_mode_shows_bosses_as_not_selected_when_empty(self):
        s = self._settings()
        s.selected_bosses = []
        s.save()

        response = self.client.get(reverse("settings"))
        content = response.content.decode()
        self.assertIn("— не выбраны —", content)

    def test_view_mode_preview_shows_real_bosses_and_time(self):
        # Antharas респает сегодня и выбран → пример содержит его имя и окно в МСК.
        s = self._settings()
        s.selected_bosses = ["Antharas", "Valakas"]
        s.save()

        response = self.client.get(reverse("settings"))
        content = response.content.decode()
        self.assertIn("Пример сообщения:", content)
        self.assertIn("Antharas", content)
        self.assertIn("МСК", content)

    def test_view_mode_preview_shows_demo_when_none_respawn_today(self):
        # Ни один выбранный босс не респает сегодня → пример с демо Antharas.
        s = self._settings()
        s.selected_bosses = ["Valakas"]
        # Убираем боссов, респающих сегодня: сдвигаем все далеко.
        for boss in (self.antharas, self.valakas, self.kernon):
            boss.respawn_start += timedelta(days=10)
            boss.respawn_end += timedelta(days=10)
            boss.save()

        response = self.client.get(reverse("settings"))
        content = response.content.decode()
        self.assertIn("Пример сообщения:", content)
        self.assertIn("Antharas", content)
        self.assertIn("21:07", content)

    def test_edit_mode_shows_form(self):
        response = self.client.get(reverse("settings"), {"edit_epic_boss": "1"})
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        # В режиме редактирования присутствует поле времени и чекбоксы боссов.
        self.assertIn('name="notification_time"', content)
        self.assertIn('name="bosses"', content)

    def test_post_saves_selected_bosses_and_returns_to_view_mode(self):
        response = self.client.post(
            reverse("settings"),
            {
                "save_epic_boss": "1",
                "is_enabled": "on",
                "notification_time": "18:00",
                "topic": "",
                "bosses": ["Antharas", "Kernon"],
                "text_template": "🎮 Сегодня респ Эпик РБ\n\nБоссы:\n{bosses}\n\nОкно респа: ~24 часа.",
            },
        )
        self.assertRedirects(response, reverse("settings"))

        s = self._settings()
        self.assertTrue(s.is_enabled)
        self.assertEqual(s.notification_time, time(18, 0))
        self.assertEqual(sorted(s.selected_bosses), ["Antharas", "Kernon"])

        # После успешного POST (редирект без edit-параметра) — режим просмотра.
        follow = self.client.get(reverse("settings"))
        self.assertEqual(follow.status_code, 200)
        self.assertNotIn('name="notification_time"', follow.content.decode())
        self.assertIn("Antharas, Kernon", follow.content.decode())

    def test_post_enabled_without_bosses_is_invalid(self):
        response = self.client.post(
            reverse("settings"),
            {
                "save_epic_boss": "1",
                "is_enabled": "on",
                "notification_time": "18:00",
                "topic": "",
                "bosses": [],
                "text_template": "🎮 Сегодня респ Эпик РБ\n\nБоссы:\n{bosses}",
            },
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Выбери хотя бы одного босса.", content)
        # Не сохранилось как включённое без боссов.
        s = self._settings()
        self.assertFalse(s.is_enabled)
