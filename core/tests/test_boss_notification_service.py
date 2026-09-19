"""Tests for the epic boss notification service."""
from datetime import datetime, time, timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    BossRespawn,
    EpicBossNotificationLog,
    EpicBossNotificationSettings,
)
from core.services import boss_notification_service, messaging_service


def _boss(
    name: str, start_offset_hours: int, boss_type: str = BossRespawn.BossType.EPIC
) -> BossRespawn:
    now = timezone.now()
    return BossRespawn.objects.create(
        boss_name=name,
        boss_type=boss_type,
        respawn_start=now + timedelta(hours=start_offset_hours),
        respawn_end=now + timedelta(hours=start_offset_hours + 1),
    )


def _boss_today(
    name: str, hour: int = 12, boss_type: str = BossRespawn.BossType.EPIC
) -> BossRespawn:
    """Босс, респающий гарантированно сегодня (в 12:00 UTC = 15:00 МСК)."""
    start = timezone.now().replace(hour=hour, minute=0, second=0, microsecond=0)
    return BossRespawn.objects.create(
        boss_name=name,
        boss_type=boss_type,
        respawn_start=start,
        respawn_end=start + timedelta(hours=1),
    )


def _boss_tomorrow(name: str, boss_type: str = BossRespawn.BossType.EPIC) -> BossRespawn:
    """Босс, респающий гарантированно НЕ сегодня (ровно через сутки)."""
    now = timezone.now()
    return BossRespawn.objects.create(
        boss_name=name,
        boss_type=boss_type,
        respawn_start=now + timedelta(days=1),
        respawn_end=now + timedelta(days=1, hours=1),
    )


@override_settings(TELEGRAM_BOT_TOKEN="12345:TESTTOKEN", PUBLIC_SITE_URL="https://example.com")
class EpicBossNotificationServiceTests(TestCase):
    """Business logic of Epic RB notifications."""

    def setUp(self):
        self.settings = boss_notification_service.get_settings()
        self.settings.is_enabled = True
        # 00:00 — уже наступило, чтобы срабатывание не блокировалось временем
        # (специфичные тесты notification_time переопределяют его явно).
        self.settings.notification_time = time(0, 0)
        self.settings.selected_bosses = ["Antharas"]
        self.settings.save()

    # ---------- get_settings / should_notify_today ----------

    def test_get_settings_creates_singleton(self):
        self.assertEqual(self.settings.pk, 1)
        self.assertEqual(EpicBossNotificationSettings.objects.count(), 1)

    def test_should_notify_today_true_when_no_log(self):
        self.assertTrue(boss_notification_service.should_notify_today())

    def test_should_notify_today_false_when_log_exists(self):
        EpicBossNotificationLog.objects.create(
            notify_date=timezone.localdate(), bosses=[], text="x", success=True,
        )
        self.assertFalse(boss_notification_service.should_notify_today())

    # ---------- generate_notification_text ----------

    def test_generate_text_substitutes_bosses_with_msk_window(self):
        bosses = [_boss("Antharas", 1), _boss("Baium", 2)]
        text = boss_notification_service.generate_notification_text(bosses)
        # Каждый босс — строка вида «Имя — с ЧЧ:ММ до ЧЧ:ММ МСК».
        self.assertIn("Antharas", text)
        self.assertIn("Baium", text)
        self.assertIn("МСК", text)
        self.assertIn("с ", text)
        self.assertIn(" до ", text)

    def test_generate_text_keeps_template_without_placeholder(self):
        self.settings.text_template = "Просто текст без переменных"
        self.settings.save()
        bosses = [_boss("Antharas", 1)]
        text = boss_notification_service.generate_notification_text(bosses)
        self.assertEqual(text, "Просто текст без переменных")

    def test_default_template_used_when_blank(self):
        self.settings.text_template = ""
        self.settings.save()
        bosses = [_boss("Antharas", 1)]
        text = boss_notification_service.generate_notification_text(bosses)
        self.assertIn("Сегодня респ Эпик РБ", text)

    # ---------- get_bosses_for_notification ----------

    def test_only_selected_bosses_respawning_today_returned(self):
        _boss_today("Antharas")
        _boss_today("Valakas")
        _boss_today("Baium")
        # Выбраны только Antharas и Baium; Valakas не выбран.
        self.settings.selected_bosses = ["Antharas", "Baium"]
        self.settings.save()

        bosses = boss_notification_service.get_bosses_for_notification()
        self.assertEqual(sorted(b.boss_name for b in bosses), ["Antharas", "Baium"])

    def test_selected_boss_not_respawning_today_excluded(self):
        _boss_today("Antharas")
        _boss_tomorrow("Valakas")  # не сегодня
        self.settings.selected_bosses = ["Antharas", "Valakas"]
        self.settings.save()

        bosses = boss_notification_service.get_bosses_for_notification()
        self.assertEqual([b.boss_name for b in bosses], ["Antharas"])

    def test_subclass_selected_boss_included(self):
        _boss_today("Kernon", boss_type=BossRespawn.BossType.SUBCLASS)
        self.settings.selected_bosses = ["Kernon"]
        self.settings.save()

        bosses = boss_notification_service.get_bosses_for_notification()
        self.assertEqual([b.boss_name for b in bosses], ["Kernon"])

    # ---------- get_notification_preview ----------

    def test_preview_uses_real_selected_bosses(self):
        _boss_today("Antharas")
        _boss_today("Valakas")
        self.settings.selected_bosses = ["Antharas", "Valakas"]
        self.settings.save()

        preview = boss_notification_service.get_notification_preview()
        self.assertIn("Antharas", preview)
        self.assertIn("Valakas", preview)

    def test_preview_falls_back_to_demo_boss(self):
        # Ни один босс не выбран или не респает сегодня → демо Antharas.
        self.settings.selected_bosses = []
        self.settings.save()

        preview = boss_notification_service.get_notification_preview()
        self.assertIn("Antharas", preview)
        self.assertIn("21:07", preview)
        self.assertIn("МСК", preview)

    # ---------- send_epic_boss_notification ----------

    @mock.patch("core.services.messaging_service.send_epic_boss_notification")
    def test_disabled_exits_without_sending(self, mock_send):
        self.settings.is_enabled = False
        self.settings.save()
        boss_notification_service.send_epic_boss_notification()
        mock_send.assert_not_called()
        self.assertEqual(EpicBossNotificationLog.objects.count(), 0)

    # ---------- notification_time (МСК) ----------

    @mock.patch("core.services.messaging_service.send_epic_boss_notification")
    def test_before_notification_time_skips(self, mock_send):
        """notification_time=18:00, сейчас 10:00 МСК → не отправляется."""
        self.settings.notification_time = time(18, 0)
        self.settings.save()
        _boss_today("Antharas")

        with mock.patch(
            "django.utils.timezone.localtime",
            return_value=timezone.make_aware(
                datetime.combine(timezone.localdate(), time(10, 0))
            ),
        ):
            boss_notification_service.send_epic_boss_notification()

        mock_send.assert_not_called()
        self.assertEqual(EpicBossNotificationLog.objects.count(), 0)

    @mock.patch("core.services.messaging_service.send_epic_boss_notification")
    def test_after_notification_time_sends(self, mock_send):
        """notification_time=18:00, сейчас 18:01 МСК → отправляется."""
        mock_send.return_value = mock.Mock()
        self.settings.notification_time = time(18, 0)
        self.settings.save()
        _boss_today("Antharas")

        with mock.patch(
            "django.utils.timezone.localtime",
            return_value=timezone.make_aware(
                datetime.combine(timezone.localdate(), time(18, 1))
            ),
        ):
            boss_notification_service.send_epic_boss_notification()

        mock_send.assert_called_once()
        self.assertEqual(EpicBossNotificationLog.objects.count(), 1)

    # ---------- Форма (notification_time обязателен) ----------

    def test_form_requires_notification_time(self):
        from core.forms import EpicBossNotificationSettingsForm

        form = EpicBossNotificationSettingsForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn("notification_time", form.errors)

    @mock.patch("core.services.messaging_service.send_epic_boss_notification")
    def test_already_sent_today_exits(self, mock_send):
        EpicBossNotificationLog.objects.create(
            notify_date=timezone.localdate(), bosses=["Antharas"], text="x", success=True,
        )
        _boss_today("Antharas")
        boss_notification_service.send_epic_boss_notification()
        mock_send.assert_not_called()
        self.assertEqual(EpicBossNotificationLog.objects.count(), 1)

    @mock.patch("core.services.messaging_service.send_epic_boss_notification")
    def test_no_selected_boss_respawns_today_exits(self, mock_send):
        # Выбранный босс не респает сегодня → не отправляем.
        _boss_tomorrow("Valakas")
        self.settings.selected_bosses = ["Antharas"]
        self.settings.save()
        boss_notification_service.send_epic_boss_notification()
        mock_send.assert_not_called()
        self.assertEqual(EpicBossNotificationLog.objects.count(), 0)

    @mock.patch("core.services.messaging_service.send_epic_boss_notification")
    def test_empty_selected_bosses_exits(self, mock_send):
        _boss_today("Antharas")
        self.settings.selected_bosses = []
        self.settings.save()
        boss_notification_service.send_epic_boss_notification()
        mock_send.assert_not_called()
        self.assertEqual(EpicBossNotificationLog.objects.count(), 0)

    @mock.patch("core.services.messaging_service.send_epic_boss_notification")
    def test_sends_and_logs_success(self, mock_send):
        mock_send.return_value = mock.Mock()
        _boss_today("Antharas")

        boss_notification_service.send_epic_boss_notification()

        mock_send.assert_called_once()
        log = EpicBossNotificationLog.objects.get()
        self.assertEqual(log.notify_date, timezone.localdate())
        self.assertEqual(log.bosses, ["Antharas"])
        self.assertTrue(log.success)

    @mock.patch("core.services.messaging_service.send_epic_boss_notification")
    def test_only_selected_bosses_in_sent_message(self, mock_send):
        """Выбран Antharas; респают Antharas и Valakas → в тексте только Antharas."""
        mock_send.return_value = mock.Mock()
        _boss_today("Antharas")
        _boss_today("Valakas")
        self.settings.selected_bosses = ["Antharas"]
        self.settings.save()

        boss_notification_service.send_epic_boss_notification()

        mock_send.assert_called_once()
        sent_text = mock_send.call_args.args[1]
        self.assertIn("Antharas", sent_text)
        self.assertNotIn("Valakas", sent_text)
        log = EpicBossNotificationLog.objects.get()
        self.assertEqual(log.bosses, ["Antharas"])

    @mock.patch("core.services.messaging_service.send_epic_boss_notification")
    def test_sent_text_contains_msk_window(self, mock_send):
        mock_send.return_value = mock.Mock()
        _boss_today("Antharas")

        boss_notification_service.send_epic_boss_notification()

        sent_text = mock_send.call_args.args[1]
        self.assertIn("Antharas", sent_text)
        self.assertIn("с ", sent_text)
        self.assertIn(" до ", sent_text)
        self.assertIn("МСК", sent_text)

    @mock.patch("core.services.messaging_service.send_epic_boss_notification")
    def test_no_active_group_logs_failure(self, mock_send):
        mock_send.side_effect = messaging_service.MessagingError("No active group")
        _boss_today("Antharas")

        boss_notification_service.send_epic_boss_notification()

        log = EpicBossNotificationLog.objects.get()
        self.assertFalse(log.success)
        self.assertEqual(log.bosses, ["Antharas"])

    # ---------- Дублирование (unique notify_date) ----------

    def test_duplicate_notify_date_is_swallowed(self):
        today = timezone.localdate()
        EpicBossNotificationLog.objects.create(
            notify_date=today, bosses=[], text="x", success=True,
        )
        # Повторная запись за тот же день не создаёт второй лог.
        created = boss_notification_service._record_log(
            notify_date=today, bosses=["Antharas"], text="y", success=True,
        )
        self.assertFalse(created)
        self.assertEqual(EpicBossNotificationLog.objects.count(), 1)

    @mock.patch("core.services.messaging_service.send_epic_boss_notification")
    def test_second_send_same_day_is_skipped(self, mock_send):
        mock_send.return_value = mock.Mock()
        _boss_today("Antharas")

        boss_notification_service.send_epic_boss_notification()
        boss_notification_service.send_epic_boss_notification()

        self.assertEqual(mock_send.call_count, 1)
        self.assertEqual(EpicBossNotificationLog.objects.count(), 1)
