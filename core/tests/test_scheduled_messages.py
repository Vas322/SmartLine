"""Tests for scheduled messages feature."""
from datetime import date, datetime, time, timedelta
from unittest import mock

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from zoneinfo import ZoneInfo

from core.admin import ScheduledMessageAdmin
from core.forms import ScheduledMessageAdminForm
from core.models import (
    OutgoingMessage,
    ScheduledMessage,
    TelegramSettings,
    TelegramTopic,
)
from core.services.scheduling_service import (
    computed_next_run,
    due_schedules,
    next_run,
    release_lock,
    try_acquire_lock,
)
from telegram_bot.bot import TelegramAPIError

MSK_TZ = ZoneInfo("Europe/Moscow")


_GROUP_CHAT_ID = -1001234567890


@override_settings(TELEGRAM_BOT_TOKEN="12345:TESTTOKEN")
class SchedulingServiceTests(TestCase):
    """Tests for next_run and due_schedules logic."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.group = TelegramSettings.objects.create(
            name="Основная группа",
            group_chat_id=_GROUP_CHAT_ID,
            is_active=True,
        )
        self.topic = TelegramTopic.objects.create(
            name="FORTS", thread_id=12, is_active=True, group=self.group
        )

    def _make_schedule(self, **kwargs) -> ScheduledMessage:
        defaults = {
            "name": "Test Schedule",
            "text": "Test message",
            "topic": self.topic,
            "weekdays": [5, 6],  # Sat, Sun
            "time": time(18, 0),
            "frequency": ScheduledMessage.Frequency.WEEKLY,
            "start_date": date(2026, 1, 5),  # Monday
            "is_active": True,
            "created_by": self.staff,
        }
        defaults.update(kwargs)
        return ScheduledMessage.objects.create(**defaults)

    def _aware_dt(self, dt: datetime) -> datetime:
        """Make datetime aware in MSK."""
        if timezone.is_naive(dt):
            return dt.replace(tzinfo=MSK_TZ)
        return dt.astimezone(MSK_TZ)

    # ---- next_run tests ----

    def test_next_run_weekly_basic(self):
        """Weekly: next matching weekday after 'after'."""
        schedule = self._make_schedule(
            weekdays=[0, 2],  # Mon, Wed
            time=time(12, 0),
            start_date=date(2026, 1, 5),  # Monday
        )
        # after = Wednesday 2026-01-07 10:00 -> next is same day at 12:00
        after = timezone.make_aware(datetime(2026, 1, 7, 10, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 1, 7, 12, 0)))

        # after = Wednesday 2026-01-07 14:00 -> next is Monday 2026-01-12 12:00
        after = timezone.make_aware(datetime(2026, 1, 7, 14, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 1, 12, 12, 0)))

    def test_next_run_weekly_end_date(self):
        """Weekly: returns None after end_date."""
        schedule = self._make_schedule(
            weekdays=[0],
            time=time(12, 0),
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 10),
        )
        after = timezone.make_aware(datetime(2026, 1, 11, 10, 0))
        next_dt = next_run(schedule, after=after)
        self.assertIsNone(next_dt)

    def test_next_run_biweekly_basic(self):
        """Biweekly: start_date + 14*n, matching weekdays."""
        schedule = self._make_schedule(
            frequency=ScheduledMessage.Frequency.BIWEEKLY,
            weekdays=[5],  # Saturday
            time=time(18, 0),
            start_date=date(2026, 1, 3),  # Saturday
        )
        # after = before first Saturday -> first Saturday
        after = timezone.make_aware(datetime(2026, 1, 1, 10, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 1, 3, 18, 0)))

        # after = first Saturday -> next is +14 days
        after = timezone.make_aware(datetime(2026, 1, 3, 19, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 1, 17, 18, 0)))

    def test_next_run_biweekly_weekday_filter(self):
        """Biweekly: only dates matching weekdays."""
        # Start on Monday, but only want Saturdays
        schedule = self._make_schedule(
            frequency=ScheduledMessage.Frequency.BIWEEKLY,
            weekdays=[5],  # Saturday only
            time=time(18, 0),
            start_date=date(2026, 1, 5),  # Monday
        )
        # First biweekly date is 2026-01-05 (Mon) - not Saturday
        # Next is 2026-01-19 (Mon) - not Saturday
        # Next is 2026-02-02 (Mon) - not Saturday
        # Should skip to first Saturday that aligns with biweekly grid
        # Actually _next_biweekly_date checks each 14-day step for matching weekday
        after = timezone.make_aware(datetime(2026, 1, 1, 10, 0))
        next_dt = next_run(schedule, after=after)
        # First biweekly Saturday after start_date: start_date=Mon 1/5, +14=Mon 1/19, +14=Mon 2/2...
        # None of these are Saturdays, so it should return None after checking 52 periods
        self.assertIsNone(next_dt)

    def test_next_run_biweekly_with_matching_weekday(self):
        """Biweekly with start_date on a matching weekday."""
        schedule = self._make_schedule(
            frequency=ScheduledMessage.Frequency.BIWEEKLY,
            weekdays=[5],  # Saturday
            time=time(18, 0),
            start_date=date(2026, 1, 3),  # Saturday
        )
        after = timezone.make_aware(datetime(2026, 1, 1, 10, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 1, 3, 18, 0)))

        after = timezone.make_aware(datetime(2026, 1, 3, 19, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 1, 17, 18, 0)))

    def test_next_run_monthly_basic(self):
        """Monthly: same day each month."""
        schedule = self._make_schedule(
            frequency=ScheduledMessage.Frequency.MONTHLY,
            weekdays=[],  # not used for monthly
            time=time(10, 0),
            start_date=date(2026, 1, 15),
        )
        after = timezone.make_aware(datetime(2026, 1, 1, 10, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 1, 15, 10, 0)))

        after = timezone.make_aware(datetime(2026, 1, 15, 11, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 2, 15, 10, 0)))

    def test_next_run_monthly_day_overflow(self):
        """Monthly: day 31 -> last day of month for short months."""
        schedule = self._make_schedule(
            frequency=ScheduledMessage.Frequency.MONTHLY,
            weekdays=[],
            time=time(10, 0),
            start_date=date(2026, 1, 31),
        )
        # February 2026 has 28 days
        after = timezone.make_aware(datetime(2026, 2, 1, 10, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 2, 28, 10, 0)))

        # March has 31 days
        after = timezone.make_aware(datetime(2026, 3, 1, 10, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 3, 31, 10, 0)))

    def test_next_run_custom_dates(self):
        """Custom dates: next date from list."""
        schedule = self._make_schedule(
            frequency=ScheduledMessage.Frequency.CUSTOM_DATES,
            weekdays=[],
            time=time(15, 0),
            start_date=date(2026, 1, 1),
            custom_dates=["2026-02-14", "2026-03-08", "2026-05-01"],
        )
        after = timezone.make_aware(datetime(2026, 1, 1, 10, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 2, 14, 15, 0)))

        after = timezone.make_aware(datetime(2026, 2, 14, 16, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 3, 8, 15, 0)))

        after = timezone.make_aware(datetime(2026, 5, 2, 10, 0))
        next_dt = next_run(schedule, after=after)
        self.assertIsNone(next_dt)  # past last custom date

    def test_next_run_custom_dates_invalid_format(self):
        """Custom dates: invalid formats are skipped with warning."""
        schedule = self._make_schedule(
            frequency=ScheduledMessage.Frequency.CUSTOM_DATES,
            weekdays=[],
            time=time(15, 0),
            start_date=date(2026, 1, 1),
            custom_dates=["invalid", "2026-02-14"],
        )
        after = timezone.make_aware(datetime(2026, 1, 1, 10, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 2, 14, 15, 0)))

    def test_next_run_inactive_schedule_returns_none(self):
        """Inactive schedule returns None."""
        schedule = self._make_schedule(is_active=False)
        after = timezone.make_aware(datetime(2026, 1, 5, 10, 0))
        next_dt = next_run(schedule, after=after)
        self.assertIsNone(next_dt)

    def test_next_run_end_date_exact_match(self):
        """End date is inclusive for the date check."""
        schedule = self._make_schedule(
            weekdays=[0],
            time=time(12, 0),
            start_date=date(2026, 1, 5),
            end_date=date(2026, 1, 12),
        )
        after = timezone.make_aware(datetime(2026, 1, 12, 10, 0))
        next_dt = next_run(schedule, after=after)
        self.assertEqual(next_dt, timezone.make_aware(datetime(2026, 1, 12, 12, 0)))

        after = timezone.make_aware(datetime(2026, 1, 12, 13, 0))
        next_dt = next_run(schedule, after=after)
        self.assertIsNone(next_dt)

    # ---- computed_next_run tests ----

    def test_computed_next_run_uses_last_sent_at(self):
        """computed_next_run considers last_sent_at."""
        schedule = self._make_schedule(
            weekdays=[0], time=time(12, 0), start_date=date(2026, 1, 5)
        )
        schedule.last_sent_at = self._aware_dt(datetime(2026, 1, 5, 12, 0))
        schedule.save()

        # Now is 2026-01-07, but last_sent_at was 2026-01-05 -> next is 2026-01-12
        with mock.patch("core.services.scheduling_service._now_msk") as mock_now:
            mock_now.return_value = self._aware_dt(datetime(2026, 1, 7, 10, 0))
            next_dt = computed_next_run(schedule)
            self.assertEqual(next_dt, self._aware_dt(datetime(2026, 1, 12, 12, 0)))

    # ---- due_schedules tests ----

    def test_due_schedules_returns_due(self):
        """due_schedules returns schedules whose time has come."""
        schedule = self._make_schedule(
            weekdays=[0], time=time(12, 0), start_date=date(2026, 1, 5)
        )
        # Now is exactly the scheduled time
        now = self._aware_dt(datetime(2026, 1, 5, 12, 0))
        due = due_schedules(now=now)
        self.assertIn(schedule, due)

    def test_due_schedules_excludes_inactive(self):
        """Inactive schedules are not due."""
        schedule = self._make_schedule(is_active=False)
        now = timezone.make_aware(datetime(2026, 1, 5, 12, 0))
        due = due_schedules(now=now)
        self.assertNotIn(schedule, due)

    def test_due_schedules_excludes_already_sent_this_minute(self):
        """If last_sent_at is in the same minute, not due again."""
        schedule = self._make_schedule(
            weekdays=[0], time=time(12, 0), start_date=date(2026, 1, 5)
        )
        schedule.last_sent_at = self._aware_dt(datetime(2026, 1, 5, 12, 0, 30))
        schedule.save()

        now = self._aware_dt(datetime(2026, 1, 5, 12, 0, 45))
        due = due_schedules(now=now)
        self.assertNotIn(schedule, due)

    def test_due_schedules_includes_if_last_sent_different_minute(self):
        """If last_sent_at was previous minute, due again."""
        schedule = self._make_schedule(
            weekdays=[0], time=time(12, 0), start_date=date(2026, 1, 5)
        )
        schedule.last_sent_at = self._aware_dt(datetime(2026, 1, 5, 11, 59, 30))
        schedule.save()

        now = self._aware_dt(datetime(2026, 1, 5, 12, 0, 10))
        due = due_schedules(now=now)
        self.assertIn(schedule, due)

    def test_due_schedules_excludes_past_end_date(self):
        """Schedules past end_date are not due."""
        schedule = self._make_schedule(
            weekdays=[0], time=time(12, 0), start_date=date(2026, 1, 5), end_date=date(2026, 1, 5)
        )
        schedule.last_sent_at = None
        schedule.save()

        now = self._aware_dt(datetime(2026, 1, 5, 12, 0))
        due = due_schedules(now=now)
        self.assertIn(schedule, due)

        now = self._aware_dt(datetime(2026, 1, 6, 12, 0))
        due = due_schedules(now=now)
        self.assertNotIn(schedule, due)


@override_settings(TELEGRAM_BOT_TOKEN="12345:TESTTOKEN")
class SendScheduledMessagesCommandTests(TestCase):
    """Tests for send_scheduled_messages management command."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.group = TelegramSettings.objects.create(
            name="Основная группа",
            group_chat_id=_GROUP_CHAT_ID,
            is_active=True,
        )
        self.topic = TelegramTopic.objects.create(
            name="FORTS", thread_id=12, is_active=True, group=self.group
        )

    def _make_schedule(self, **kwargs) -> ScheduledMessage:
        defaults = {
            "name": "Test Schedule",
            "text": "Test message",
            "topic": self.topic,
            "weekdays": [5],
            "time": time(18, 0),
            "frequency": ScheduledMessage.Frequency.WEEKLY,
            "start_date": date(2026, 1, 3),
            "is_active": True,
            "created_by": self.staff,
        }
        defaults.update(kwargs)
        return ScheduledMessage.objects.create(**defaults)

    @mock.patch("core.management.commands.send_scheduled_messages.send_scheduled_message")
    @mock.patch("core.management.commands.send_scheduled_messages.due_schedules")
    @mock.patch("core.management.commands.send_scheduled_messages.try_acquire_lock", return_value=True)
    @mock.patch("core.management.commands.send_scheduled_messages.release_lock")
    def test_command_calls_send_for_due_schedules(self, mock_release, mock_lock, mock_due, mock_send):
        """Command calls send_scheduled_message for each due schedule."""
        schedule = self._make_schedule()
        mock_due.return_value = [schedule]
        mock_send.return_value = mock.MagicMock()

        from django.core.management import call_command
        call_command("send_scheduled_messages")

        mock_send.assert_called_once_with(schedule)

    @mock.patch("core.management.commands.send_scheduled_messages.send_scheduled_message")
    @mock.patch("core.management.commands.send_scheduled_messages.due_schedules")
    @mock.patch("core.management.commands.send_scheduled_messages.try_acquire_lock", return_value=True)
    @mock.patch("core.management.commands.send_scheduled_messages.release_lock")
    def test_command_continues_on_error(self, mock_release, mock_lock, mock_due, mock_send):
        """Command continues to next schedule if one fails."""
        schedule1 = self._make_schedule(name="Schedule 1")
        schedule2 = self._make_schedule(name="Schedule 2")
        mock_due.return_value = [schedule1, schedule2]

        from core.services.messaging_service import MessagingError
        mock_send.side_effect = [MessagingError("fail"), mock.MagicMock()]

        from django.core.management import call_command
        call_command("send_scheduled_messages")

        self.assertEqual(mock_send.call_count, 2)

    @mock.patch("core.management.commands.send_scheduled_messages.try_acquire_lock", return_value=False)
    def test_command_exits_if_lock_not_acquired(self, mock_lock):
        """Command exits silently if advisory lock not acquired."""
        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("send_scheduled_messages", stdout=out)
        self.assertIn("Another instance is running", out.getvalue())

    @mock.patch("core.management.commands.send_scheduled_messages.try_acquire_lock", return_value=True)
    @mock.patch("core.management.commands.send_scheduled_messages.release_lock")
    @mock.patch("core.management.commands.send_scheduled_messages.due_schedules", return_value=[])
    def test_command_releases_lock_on_exit(self, mock_due, mock_release, mock_lock):
        """Command releases lock even if no due schedules."""
        from django.core.management import call_command
        call_command("send_scheduled_messages")
        mock_release.assert_called_once()

    @mock.patch("core.management.commands.send_scheduled_messages.try_acquire_lock", return_value=True)
    @mock.patch("core.management.commands.send_scheduled_messages.release_lock")
    @mock.patch("core.management.commands.send_scheduled_messages.due_schedules")
    @mock.patch("core.management.commands.send_scheduled_messages.send_scheduled_message", side_effect=Exception("boom"))
    def test_command_releases_lock_on_exception(self, mock_send, mock_due, mock_release, mock_lock):
        """Command releases lock even if unexpected exception occurs."""
        schedule = self._make_schedule()
        mock_due.return_value = [schedule]

        from django.core.management import call_command
        from io import StringIO

        out = StringIO()
        call_command("send_scheduled_messages", stdout=out)
        mock_release.assert_called_once()
        self.assertIn("Unexpected error", out.getvalue())


@override_settings(TELEGRAM_BOT_TOKEN="12345:TESTTOKEN")
class SendScheduledMessageTests(TestCase):
    """Tests for messaging_service.send_scheduled_message."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.group = TelegramSettings.objects.create(
            name="Основная группа",
            group_chat_id=_GROUP_CHAT_ID,
            is_active=True,
        )
        self.topic = TelegramTopic.objects.create(
            name="FORTS", thread_id=12, is_active=True, group=self.group
        )
        self.schedule = ScheduledMessage.objects.create(
            name="Test Schedule",
            text="Test message",
            topic=self.topic,
            weekdays=[5],
            time=time(18, 0),
            frequency=ScheduledMessage.Frequency.WEEKLY,
            start_date=date(2026, 1, 3),
            is_active=True,
            created_by=self.staff,
        )

    def _mock_bot(self, message_id: int = 555):
        return mock.patch("telegram_bot.bot.TelegramBot")

    def test_send_scheduled_message_success(self):
        """Creates OutgoingMessage with source=SCHEDULED, scheduled_message, user=None,
        thread_id from topic, chat_id from active group; updates last_sent_at."""
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.return_value = {
                "ok": True,
                "result": {"message_id": 555},
            }

            from core.services.messaging_service import send_scheduled_message
            outgoing = send_scheduled_message(self.schedule)

        # Telegram вызван с chat_id активной группы и thread_id из темы
        _, kwargs = bot_instance.send_message.call_args
        self.assertEqual(kwargs["chat_id"], _GROUP_CHAT_ID)
        self.assertEqual(kwargs["message_thread_id"], 12)

        # Аудит-запись
        om = OutgoingMessage.objects.get(pk=outgoing.pk)
        self.assertEqual(om.source, OutgoingMessage.Source.SCHEDULED)
        self.assertEqual(om.scheduled_message, self.schedule)
        self.assertIsNone(om.sent_by)
        self.assertEqual(om.telegram_chat_id, _GROUP_CHAT_ID)
        self.assertEqual(om.telegram_message_id, 555)
        self.assertEqual(om.topic_name, "FORTS")
        self.assertEqual(om.status, OutgoingMessage.Status.SENT)

        # last_sent_at обновлён
        self.schedule.refresh_from_db()
        self.assertIsNotNone(self.schedule.last_sent_at)

    def test_send_scheduled_message_uses_active_group_chat_id(self):
        """chat_id берётся из активной TelegramSettings."""
        inactive = TelegramSettings.objects.create(
            name="Неактивная группа",
            group_chat_id=-1005556667777,
            is_active=False,
        )
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.return_value = {
                "ok": True,
                "result": {"message_id": 556},
            }

            from core.services.messaging_service import send_scheduled_message
            send_scheduled_message(self.schedule)

        _, kwargs = bot_instance.send_message.call_args
        self.assertEqual(kwargs["chat_id"], _GROUP_CHAT_ID)
        self.assertNotEqual(kwargs["chat_id"], inactive.group_chat_id)

    def test_send_scheduled_message_telegram_error(self):
        """Telegram error -> OutgoingMessage with ERROR status, MessagingError raised."""
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.side_effect = TelegramAPIError("api down")

            from core.services.messaging_service import MessagingError, send_scheduled_message
            with self.assertRaises(MessagingError):
                send_scheduled_message(self.schedule)

        om = OutgoingMessage.objects.get()
        self.assertEqual(om.status, OutgoingMessage.Status.ERROR)
        self.assertIn("api down", om.error_text)
        self.assertEqual(om.source, OutgoingMessage.Source.SCHEDULED)
        self.assertEqual(om.scheduled_message, self.schedule)

        # last_sent_at не обновляется при ошибке
        self.schedule.refresh_from_db()
        self.assertIsNone(self.schedule.last_sent_at)

    def test_send_scheduled_message_without_active_group_errors(self):
        """Без активной группы -> MessagingError, Telegram не вызывается."""
        TelegramSettings.objects.all().delete()
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            from core.services.messaging_service import MessagingError, send_scheduled_message
            with self.assertRaises(MessagingError):
                send_scheduled_message(self.schedule)
            BotMock.return_value.send_message.assert_not_called()
        self.assertEqual(OutgoingMessage.objects.count(), 0)

    def test_send_scheduled_message_finalize_failure_rolls_back_atomic(self):
        """Падение save финализации OutgoingMessage внутри atomic откатывает
        транзакцию: last_sent_at не обновляется, запись остаётся PENDING,
        исключение пробрасывается."""
        with mock.patch("telegram_bot.bot.TelegramBot") as BotMock:
            bot_instance = BotMock.return_value
            bot_instance.send_message.return_value = {
                "ok": True,
                "result": {"message_id": 555},
            }

            # Мокаем save финализации: первый create успешен, последующий save падает.
            real_save = OutgoingMessage.save
            calls = {"count": 0}

            def flaky_save(instance, *args, **kwargs):
                calls["count"] += 1
                if calls["count"] > 1:
                    raise RuntimeError("db down on finalize")
                return real_save(instance, *args, **kwargs)

            from core.services.messaging_service import send_scheduled_message
            with mock.patch.object(OutgoingMessage, "save", autospec=True, side_effect=flaky_save):
                with self.assertRaises(RuntimeError):
                    send_scheduled_message(self.schedule)

        # Аудит-запись создана (PENDING, create успешен), но не зафиксирована как SENT.
        om = OutgoingMessage.objects.get()
        self.assertEqual(om.status, OutgoingMessage.Status.PENDING)
        self.assertNotEqual(om.status, OutgoingMessage.Status.SENT)

        # last_sent_at не обновлён — транзакция откатилась.
        self.schedule.refresh_from_db()
        self.assertIsNone(self.schedule.last_sent_at)


@override_settings(TELEGRAM_BOT_TOKEN="12345:TESTTOKEN")
class ScheduledMessageModelTests(TestCase):
    """Tests for ScheduledMessage model."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.group = TelegramSettings.objects.create(
            name="Основная группа",
            group_chat_id=_GROUP_CHAT_ID,
            is_active=True,
        )
        self.topic = TelegramTopic.objects.create(
            name="FORTS", thread_id=12, is_active=True, group=self.group
        )

    def test_str(self):
        schedule = ScheduledMessage.objects.create(
            name="Test",
            text="Text",
            weekdays=[0],
            time=time(12, 0),
            frequency=ScheduledMessage.Frequency.WEEKLY,
            start_date=date(2026, 1, 5),
            created_by=self.staff,
        )
        self.assertEqual(str(schedule), "Test")

    def test_default_values(self):
        schedule = ScheduledMessage.objects.create(
            name="Test",
            text="Text",
            weekdays=[0],
            time=time(12, 0),
            start_date=date(2026, 1, 5),
            created_by=self.staff,
        )
        self.assertEqual(schedule.frequency, ScheduledMessage.Frequency.WEEKLY)
        self.assertTrue(schedule.is_active)
        self.assertEqual(schedule.weekdays, [0])
        self.assertEqual(schedule.custom_dates, [])
        self.assertIsNone(schedule.end_date)
        self.assertIsNone(schedule.topic)
        self.assertIsNone(schedule.last_sent_at)

    def test_ordering(self):
        """Default ordering by name."""
        ScheduledMessage.objects.create(
            name="B Schedule", text="Text", weekdays=[0], time=time(12, 0),
            start_date=date(2026, 1, 5), created_by=self.staff
        )
        ScheduledMessage.objects.create(
            name="A Schedule", text="Text", weekdays=[0], time=time(12, 0),
            start_date=date(2026, 1, 5), created_by=self.staff
        )
        names = list(ScheduledMessage.objects.values_list("name", flat=True))
        self.assertEqual(names, ["A Schedule", "B Schedule"])

    def test_clean_valid_weekdays(self):
        """Valid weekdays pass clean()."""
        schedule = ScheduledMessage(
            name="Test", text="Text", weekdays=[0, 1, 6],
            time=time(12, 0), start_date=date(2026, 1, 5), created_by=self.staff,
        )
        schedule.full_clean()

    def test_clean_rejects_out_of_range_weekday(self):
        """Weekday outside 0..6 is rejected."""
        schedule = ScheduledMessage(
            name="Test", text="Text", weekdays=[7],
            time=time(12, 0), start_date=date(2026, 1, 5), created_by=self.staff,
        )
        with self.assertRaisesMessage(
            ValidationError, "Дни недели должны быть целыми числами от 0 (Пн) до 6 (Вс)."
        ):
            schedule.full_clean()

    def test_clean_rejects_non_integer_weekday(self):
        """Non-integer weekday is rejected."""
        schedule = ScheduledMessage(
            name="Test", text="Text", weekdays=["1"],
            time=time(12, 0), start_date=date(2026, 1, 5), created_by=self.staff,
        )
        with self.assertRaisesMessage(
            ValidationError, "Дни недели должны быть целыми числами от 0 (Пн) до 6 (Вс)."
        ):
            schedule.full_clean()

    def test_clean_rejects_duplicate_weekdays(self):
        """Duplicate weekdays are rejected."""
        schedule = ScheduledMessage(
            name="Test", text="Text", weekdays=[0, 0],
            time=time(12, 0), start_date=date(2026, 1, 5), created_by=self.staff,
        )
        with self.assertRaisesMessage(ValidationError, "Дни недели не должны повторяться."):
            schedule.full_clean()

    def test_clean_rejects_empty_weekdays_for_weekly(self):
        """WEEKLY: пустой weekdays отклоняется — иначе расписание молча не сработает."""
        schedule = ScheduledMessage(
            name="Test", text="Text", weekdays=[],
            time=time(12, 0), start_date=date(2026, 1, 5),
            frequency=ScheduledMessage.Frequency.WEEKLY, created_by=self.staff,
        )
        with self.assertRaisesMessage(
            ValidationError,
            "Для периодического расписания укажите хотя бы один день недели.",
        ):
            schedule.full_clean()

    def test_clean_rejects_empty_weekdays_for_biweekly(self):
        """BIWEEKLY: пустой weekdays отклоняется."""
        schedule = ScheduledMessage(
            name="Test", text="Text", weekdays=[],
            time=time(12, 0), start_date=date(2026, 1, 5),
            frequency=ScheduledMessage.Frequency.BIWEEKLY, created_by=self.staff,
        )
        with self.assertRaisesMessage(
            ValidationError,
            "Для периодического расписания укажите хотя бы один день недели.",
        ):
            schedule.full_clean()

    def test_updated_by_saves(self):
        """При создании модели updated_by сохраняется в БД."""
        updater = User.objects.create_user(
            username="updater", password="test-password-123", is_staff=True
        )
        schedule = ScheduledMessage.objects.create(
            name="Test",
            text="Text",
            weekdays=[0],
            time=time(12, 0),
            start_date=date(2026, 1, 5),
            created_by=self.staff,
            updated_by=updater,
        )
        schedule.refresh_from_db()
        self.assertEqual(schedule.updated_by, updater)


@override_settings(TELEGRAM_BOT_TOKEN="12345:TESTTOKEN")
class ScheduledMessageAdminFormTests(TestCase):
    """Tests for the admin form used on the ScheduledMessage change form."""

    def setUp(self):
        self.group = TelegramSettings.objects.create(
            name="Основная группа",
            group_chat_id=_GROUP_CHAT_ID,
            is_active=True,
        )
        self.topic = TelegramTopic.objects.create(
            name="FORTS", thread_id=12, is_active=True, group=self.group
        )

    def _form_data(self, **kwargs) -> dict:
        data = {
            "name": "Test Schedule",
            "text": "Test message",
            "topic": self.topic.pk,
            "time": "18:00",
            "frequency": ScheduledMessage.Frequency.WEEKLY,
            "start_date": "2026-01-05",
            "is_active": True,
        }
        data.update(kwargs)
        return data

    def test_weekdays_saved_as_json_list(self):
        """weekdays выбираются чекбоксами и сохраняются как JSON-список int."""
        form = ScheduledMessageAdminForm(
            data=self._form_data(weekdays=["0", "2", "6"])
        )
        self.assertTrue(form.is_valid(), form.errors)
        schedule = form.save()
        self.assertEqual(schedule.weekdays, [0, 2, 6])

    def test_weekdays_required_for_weekly(self):
        """WEEKLY без выбранных дней — понятная ошибка формы."""
        form = ScheduledMessageAdminForm(
            data=self._form_data(weekdays=[])
        )
        self.assertFalse(form.is_valid())
        self.assertIn("weekdays", form.errors)
        self.assertIn(
            "Укажите хотя бы один день недели.", form.errors["weekdays"]
        )

    def test_weekdays_required_for_biweekly(self):
        """BIWEEKLY без выбранных дней — понятная ошибка формы."""
        form = ScheduledMessageAdminForm(
            data=self._form_data(
                frequency=ScheduledMessage.Frequency.BIWEEKLY,
                weekdays=[],
            )
        )
        self.assertFalse(form.is_valid())
        self.assertIn("weekdays", form.errors)
        self.assertIn(
            "Укажите хотя бы один день недели.", form.errors["weekdays"]
        )

    def test_weekdays_not_required_for_monthly(self):
        """MONTHLY не требует выбора дней недели."""
        form = ScheduledMessageAdminForm(
            data=self._form_data(
                frequency=ScheduledMessage.Frequency.MONTHLY,
                weekdays=[],
            )
        )
        self.assertTrue(form.is_valid(), form.errors)
        schedule = form.save()
        self.assertEqual(schedule.weekdays, [])

    def test_custom_dates_saved_as_json_list(self):
        """custom_dates из нескольких полей ввода сохраняются как JSON-список."""
        data = self._form_data(
            frequency=ScheduledMessage.Frequency.CUSTOM_DATES,
            weekdays=[],
        )
        data["custom_dates_0"] = "2026-02-14"
        data["custom_dates_1"] = "2026-03-08"
        form = ScheduledMessageAdminForm(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        schedule = form.save()
        self.assertEqual(schedule.custom_dates, ["2026-02-14", "2026-03-08"])

    def test_custom_dates_empty_saved_as_empty_list(self):
        """Пустой набор custom_dates сохраняется как пустой JSON-список."""
        form = ScheduledMessageAdminForm(
            data=self._form_data(
                frequency=ScheduledMessage.Frequency.CUSTOM_DATES,
                weekdays=[],
            )
        )
        self.assertTrue(form.is_valid(), form.errors)
        schedule = form.save()
        self.assertEqual(schedule.custom_dates, [])

    def test_custom_dates_invalid_format_error(self):
        """Невалидная дата в custom_dates — понятная ошибка."""
        data = self._form_data(
            frequency=ScheduledMessage.Frequency.CUSTOM_DATES,
            weekdays=[],
        )
        data["custom_dates_0"] = "not-a-date"
        form = ScheduledMessageAdminForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("custom_dates", form.errors)
        self.assertIn("неверном формате", form.errors["custom_dates"][0])


@override_settings(TELEGRAM_BOT_TOKEN="12345:TESTTOKEN")
class ScheduledMessageAdminTests(TestCase):
    """Tests for ScheduledMessageAdmin.save_model (created_by / updated_by)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.group = TelegramSettings.objects.create(
            name="Основная группа",
            group_chat_id=_GROUP_CHAT_ID,
            is_active=True,
        )
        self.topic = TelegramTopic.objects.create(
            name="FORTS", thread_id=12, is_active=True, group=self.group
        )
        self.site = AdminSite()
        self.admin = ScheduledMessageAdmin(ScheduledMessage, self.site)

    def _request(self):
        request = RequestFactory().post("/")
        request.user = self.user
        return request

    def _make_schedule(self, **kwargs) -> ScheduledMessage:
        defaults = {
            "name": "Test Schedule",
            "text": "Test message",
            "topic": self.topic,
            "weekdays": [5],
            "time": time(18, 0),
            "frequency": ScheduledMessage.Frequency.WEEKLY,
            "start_date": date(2026, 1, 3),
            "is_active": True,
        }
        defaults.update(kwargs)
        return ScheduledMessage(**defaults)

    def test_save_model_sets_created_by_and_updated_by_on_create(self):
        """При создании проставляются и created_by, и updated_by."""
        obj = self._make_schedule()
        self.admin.save_model(self._request(), obj, None, change=False)
        obj.refresh_from_db()
        self.assertEqual(obj.created_by, self.user)
        self.assertEqual(obj.updated_by, self.user)

    def test_save_model_updates_updated_by_on_change(self):
        """При изменении обновляется updated_by, а created_by остаётся прежним."""
        original = self.user
        creator = User.objects.create_user(
            username="creator", password="test-password-123", is_staff=True
        )
        obj = ScheduledMessage.objects.create(
            name="Test Schedule",
            text="Test message",
            topic=self.topic,
            weekdays=[5],
            time=time(18, 0),
            frequency=ScheduledMessage.Frequency.WEEKLY,
            start_date=date(2026, 1, 3),
            is_active=True,
            created_by=creator,
        )
        self.admin.save_model(self._request(), obj, None, change=True)
        obj.refresh_from_db()
        self.assertEqual(obj.created_by, creator)
        self.assertEqual(obj.updated_by, original)


@override_settings(TELEGRAM_BOT_TOKEN="12345:TESTTOKEN")
class AdvisoryLockTests(TestCase):
    """Tests for PostgreSQL advisory lock."""

    @mock.patch("django.db.connection")
    def test_try_acquire_lock(self, mock_connection):
        """First call acquires lock, second fails."""
        mock_connection.vendor = "postgresql"
        mock_cursor = mock.MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (True,)

        self.assertTrue(try_acquire_lock())
        mock_cursor.execute.assert_called_with("SELECT pg_try_advisory_lock(%s)", [123456789])

        mock_cursor.fetchone.return_value = (False,)
        self.assertFalse(try_acquire_lock())

    @mock.patch("django.db.connection")
    def test_release_lock(self, mock_connection):
        """Release lock allows re-acquisition."""
        mock_connection.vendor = "postgresql"
        mock_cursor = mock.MagicMock()
        mock_connection.cursor.return_value.__enter__.return_value = mock_cursor

        try_acquire_lock()
        release_lock()
        mock_cursor.execute.assert_called_with("SELECT pg_advisory_unlock(%s)", [123456789])


@override_settings(TELEGRAM_BOT_TOKEN="12345:TESTTOKEN")
class AdvisoryLockSqliteTests(TestCase):
    """Tests for advisory lock behavior on non-PostgreSQL vendors (SQLite/dev)."""

    @mock.patch("django.db.connection")
    def test_try_acquire_lock_sqlite_returns_true_without_sql(self, mock_connection):
        """On SQLite the lock is treated as free and no SQL is executed."""
        mock_connection.vendor = "sqlite"
        self.assertTrue(try_acquire_lock())
        mock_connection.cursor.assert_not_called()

    @mock.patch("django.db.connection")
    def test_release_lock_sqlite_is_noop(self, mock_connection):
        """On SQLite release_lock does nothing and does not raise."""
        mock_connection.vendor = "sqlite"
        release_lock()
        mock_connection.cursor.assert_not_called()


@override_settings(TELEGRAM_BOT_TOKEN="12345:TESTTOKEN")
class RunDueSchedulesTests(TestCase):
    """Tests for the in-process scheduler cycle (run_due_schedules)."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.group = TelegramSettings.objects.create(
            name="Основная группа",
            group_chat_id=_GROUP_CHAT_ID,
            is_active=True,
        )
        self.topic = TelegramTopic.objects.create(
            name="FORTS", thread_id=12, is_active=True, group=self.group
        )

    def _make_schedule(self, **kwargs) -> ScheduledMessage:
        defaults = {
            "name": "Test Schedule",
            "text": "Test message",
            "topic": self.topic,
            "weekdays": [5],
            "time": time(18, 0),
            "frequency": ScheduledMessage.Frequency.WEEKLY,
            "start_date": date(2026, 1, 3),
            "is_active": True,
            "created_by": self.staff,
        }
        defaults.update(kwargs)
        return ScheduledMessage.objects.create(**defaults)

    @mock.patch("core.services.messaging_service.send_scheduled_message")
    @mock.patch("core.services.scheduling_service.due_schedules")
    def test_run_due_schedules_sends_each_due(self, mock_due, mock_send):
        """run_due_schedules sends each due schedule."""
        schedule1 = self._make_schedule(name="Schedule 1")
        schedule2 = self._make_schedule(name="Schedule 2")
        mock_due.return_value = [schedule1, schedule2]

        from core.services.scheduling_service import run_due_schedules
        run_due_schedules()

        mock_send.assert_has_calls(
            [mock.call(schedule1), mock.call(schedule2)]
        )

    @mock.patch("core.services.messaging_service.send_scheduled_message")
    @mock.patch("core.services.scheduling_service.due_schedules")
    def test_run_due_schedules_continues_on_messaging_error(self, mock_due, mock_send):
        """run_due_schedules continues to next schedule on MessagingError."""
        schedule1 = self._make_schedule(name="Schedule 1")
        schedule2 = self._make_schedule(name="Schedule 2")
        mock_due.return_value = [schedule1, schedule2]

        from core.services.messaging_service import MessagingError
        mock_send.side_effect = [MessagingError("fail"), mock.MagicMock()]

        from core.services.scheduling_service import run_due_schedules
        run_due_schedules()  # not expected to raise

        self.assertEqual(mock_send.call_count, 2)

    @mock.patch("core.services.messaging_service.send_scheduled_message")
    @mock.patch("core.services.scheduling_service.due_schedules")
    def test_run_due_schedules_continues_on_unexpected_error(self, mock_due, mock_send):
        """run_due_schedules continues to next schedule on unexpected Exception."""
        schedule1 = self._make_schedule(name="Schedule 1")
        schedule2 = self._make_schedule(name="Schedule 2")
        mock_due.return_value = [schedule1, schedule2]

        mock_send.side_effect = [Exception("boom"), mock.MagicMock()]

        from core.services.scheduling_service import run_due_schedules
        run_due_schedules()  # not expected to raise

        self.assertEqual(mock_send.call_count, 2)

    @mock.patch("core.services.messaging_service.send_scheduled_message")
    @mock.patch("core.services.scheduling_service.due_schedules", return_value=[])
    def test_run_due_schedules_no_due_sends_nothing(self, mock_due, mock_send):
        """run_due_schedules does nothing when no schedules are due."""
        from core.services.scheduling_service import run_due_schedules
        run_due_schedules()
        mock_send.assert_not_called()