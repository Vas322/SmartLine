"""Tests for the Smartline web interface - TelegramSettingsAdminTests class."""

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


_XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)



class TelegramSettingsAdminTests(TestCase):
    """Staff (КЛ) должен иметь возможность управлять группами (и темами внутри них)."""

    def setUp(self):
        from core.models import TelegramSettings

        self.settings = TelegramSettings.objects.create(
            name="Основная группа",
            group_chat_id=-1001234567890,
            is_active=True,
        )
        self.staff_user = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.non_staff_user = User.objects.create_user(
            username="player", password="test-password-123", is_staff=False
        )

    def test_staff_can_open_change_form_for_existing_group(self):
        """Staff (is_staff) видит change/ без 403 даже без явных прав на change."""
        self.client.login(username="kl", password="test-password-123")
        response = self.client.get(
            reverse("admin:core_telegramsettings_change", args=[self.settings.pk])
        )
        self.assertEqual(response.status_code, 200)

    def test_staff_change_form_contains_group_fields(self):
        """Форма change содержит поля name, group_chat_id и is_active."""
        self.client.login(username="kl", password="test-password-123")
        response = self.client.get(
            reverse("admin:core_telegramsettings_change", args=[self.settings.pk])
        )
        content = response.content.decode()
        self.assertIn("id_name", content)
        self.assertIn("id_group_chat_id", content)
        self.assertIn("id_is_active", content)

    def test_staff_change_form_shows_topics_inline(self):
        """Инлайн тем группы присутствует на форме change группы."""
        from core.models import TelegramTopic

        TelegramTopic.objects.create(
            name="FORTS", thread_id=12, is_active=True, group=self.settings
        )
        self.client.login(username="kl", password="test-password-123")
        response = self.client.get(
            reverse("admin:core_telegramsettings_change", args=[self.settings.pk])
        )
        content = response.content.decode()
        self.assertIn("FORTS", content)

    def test_non_staff_cannot_open_change_form(self):
        """Обычный пользователь (не staff) не имеет доступа к change/.

        Django admin для неавторизованного в админке пользователя
        перенаправляет на login страницу админки (302), а не отдаёт 403.
        """
        self.client.login(username="player", password="test-password-123")
        response = self.client.get(
            reverse("admin:core_telegramsettings_change", args=[self.settings.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response.url)

    def test_staff_can_save_group(self):
        """Staff может сохранить изменённую группу (POST не 403)."""
        self.client.login(username="kl", password="test-password-123")
        response = self.client.post(
            reverse("admin:core_telegramsettings_change", args=[self.settings.pk]),
            {
                "name": "Основная группа",
                "group_chat_id": "-1009876543210",
                "is_active": "on",
                "topics-TOTAL_FORMS": "0",
                "topics-INITIAL_FORMS": "0",
                "topics-MIN_NUM_FORMS": "0",
                "topics-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.settings.refresh_from_db()
        self.assertEqual(self.settings.group_chat_id, -1009876543210)

    def test_staff_can_add_group(self):
        """Staff может создать новую группу (has_add_permission=True)."""
        from core.models import TelegramSettings

        self.client.login(username="kl", password="test-password-123")
        response = self.client.post(
            reverse("admin:core_telegramsettings_add"),
            {
                "name": "Вторая группа",
                "group_chat_id": "-1005556667777",
                "is_active": "",
                "topics-TOTAL_FORMS": "0",
                "topics-INITIAL_FORMS": "0",
                "topics-MIN_NUM_FORMS": "0",
                "topics-MAX_NUM_FORMS": "1000",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            TelegramSettings.objects.filter(name="Вторая группа").exists()
        )

    def test_only_one_active_group_in_admin(self):
        """Попытка сделать две активные группы через админку отклоняется (констрейнт БД)."""
        from core.models import TelegramSettings

        self.client.login(username="kl", password="test-password-123")
        self.client.post(
            reverse("admin:core_telegramsettings_add"),
            {
                "name": "Конфликтная группа",
                "group_chat_id": "-1005556667778",
                "is_active": "on",
                "topics-TOTAL_FORMS": "1",
                "topics-INITIAL_FORMS": "0",
                "topics-MIN_NUM_FORMS": "0",
                "topics-MAX_NUM_FORMS": "1000",
            },
        )
        # Новая активная группа не сохраняется (конфликт с существующей активной).
        self.assertEqual(TelegramSettings.objects.filter(is_active=True).count(), 1)
