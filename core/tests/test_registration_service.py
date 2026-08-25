"""Tests for the registration processing service."""
from datetime import datetime, time
from decimal import Decimal
from unittest.mock import patch, Mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import (
    Player,
    ProcessingError,
    Registration,
    RegistrationRate,
    TelegramMessage,
)
from core.services.activity_service import (
    ProcessResultStatus,
    process_registration_edit,
    process_registration_message,
)


def _make_message_date(hour=12, minute=0):
    """Create a timezone-aware datetime for testing."""
    return timezone.make_aware(datetime(2024, 1, 15, hour, minute))


@override_settings(ADMIN_TELEGRAM_CHAT_IDS="", TELEGRAM_BOT_TOKEN="")
class ProcessRegistrationMessageTests(TestCase):
    def setUp(self):
        RegistrationRate.objects.all().delete()
        RegistrationRate.objects.create(
            start_time=time(0, 0),
            end_time=time(23, 59),
            rate_kk=Decimal("10.00"),
            active=True,
            order=0,
        )

    def _process(
        self,
        text="рега 2 кланами атака форта",
        chat_id=1,
        message_id=1,
        user_id=100,
        username="test_user",
        has_photo=True,
        photo_file_id="photo123",
        message_thread_id=None,
        message_date=None,
    ):
        if message_date is None:
            message_date = _make_message_date()
        return process_registration_message(
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            username=username,
            text=text,
            message_date=message_date,
            has_photo=has_photo,
            photo_file_id=photo_file_id,
            message_thread_id=message_thread_id,
        )

    def test_valid_registration_creates_record(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        result = self._process()

        self.assertEqual(result.status, ProcessResultStatus.REGISTRATION_CREATED)
        self.assertEqual(Registration.objects.count(), 1)
        reg = Registration.objects.get()
        self.assertEqual(reg.player.nickname, "Swettka")
        self.assertEqual(reg.clans_count, 2)
        self.assertEqual(reg.payment_kk, Decimal("20.00"))
        self.assertEqual(reg.description, "атака форта")
        self.assertEqual(reg.photo_file_id, "photo123")
        self.assertEqual(reg.telegram_message, result.telegram_message)
        self.assertEqual(
            result.telegram_message.status,
            TelegramMessage.Status.PROCESSED,
        )

    def test_registration_payment_calculated_from_rate(self):
        """Payment = clans_count * rate_kk."""
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        self._process("рега 3 кланов")
        reg = Registration.objects.get()
        self.assertEqual(reg.payment_kk, Decimal("30.00"))

    def test_no_photo_returns_validation_error(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        result = self._process(has_photo=False, photo_file_id=None)

        self.assertEqual(result.status, ProcessResultStatus.VALIDATION_ERROR)
        self.assertEqual(Registration.objects.count(), 0)
        error = ProcessingError.objects.get()
        self.assertEqual(error.reason, "registration_no_screenshot")
        self.assertEqual(
            result.telegram_message.status,
            TelegramMessage.Status.ERROR,
        )

    def test_unregistered_sender_returns_validation_error(self):
        # No player with user_id=100
        result = self._process(user_id=100)

        self.assertEqual(result.status, ProcessResultStatus.VALIDATION_ERROR)
        self.assertEqual(Registration.objects.count(), 0)
        error = ProcessingError.objects.get()
        self.assertEqual(error.reason, "registration_unregistered_sender")
        self.assertEqual(
            result.telegram_message.status,
            TelegramMessage.Status.ERROR,
        )

    def test_duplicate_message_returns_edit_ignored(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        first = self._process(message_id=1)
        self.assertEqual(first.status, ProcessResultStatus.REGISTRATION_CREATED)

        second = self._process(message_id=1, text="рега 5 кланов другое описание")
        self.assertEqual(second.status, ProcessResultStatus.EDIT_IGNORED)
        self.assertEqual(Registration.objects.count(), 1)
        # Original registration preserved
        reg = Registration.objects.get()
        self.assertEqual(reg.clans_count, 2)
        self.assertEqual(reg.description, "атака форта")

    def test_parse_error_creates_processing_error(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        # Missing clans count
        result = self._process(text="рега")

        self.assertEqual(result.status, ProcessResultStatus.PROCESSING_ERROR)
        self.assertEqual(Registration.objects.count(), 0)
        error = ProcessingError.objects.get()
        self.assertEqual(error.reason, "registration_missing_clans_count")

    def test_invalid_clans_count_creates_processing_error(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        result = self._process(text="рега ноль кланов")

        self.assertEqual(result.status, ProcessResultStatus.PROCESSING_ERROR)
        error = ProcessingError.objects.get()
        self.assertEqual(error.reason, "registration_invalid_clans_count")

    def test_missing_keyword_creates_processing_error(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        result = self._process(text="2 клана атака")

        self.assertEqual(result.status, ProcessResultStatus.PROCESSING_ERROR)
        error = ProcessingError.objects.get()
        self.assertEqual(error.reason, "registration_missing_keyword")

    @patch("core.services.activity_service.notify_group_reply")
    def test_notification_sent_on_no_photo(self, mock_notify):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        self._process(has_photo=False, photo_file_id=None, message_thread_id=42)

        mock_notify.assert_called_once()
        args, kwargs = mock_notify.call_args
        self.assertEqual(kwargs.get("message_thread_id"), 42)
        self.assertIn("скриншот", args[1])

    @patch("core.services.activity_service.notify_group_reply")
    def test_notification_sent_on_unregistered_sender(self, mock_notify):
        self._process(user_id=999, message_thread_id=42)

        mock_notify.assert_called_once()
        args, kwargs = mock_notify.call_args
        self.assertEqual(kwargs.get("message_thread_id"), 42)
        self.assertIn("не зарегистрированы", args[1])

    @patch("core.services.activity_service.notify_group_reply")
    def test_notification_sent_on_parse_error(self, mock_notify):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        self._process(text="рега", message_thread_id=42)

        mock_notify.assert_called_once()
        args, kwargs = mock_notify.call_args
        self.assertEqual(kwargs.get("message_thread_id"), 42)
        self.assertIn("кланов", args[1])

    def test_registration_links_to_telegram_message(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        result = self._process(message_id=12345)

        tm = result.telegram_message
        self.assertEqual(tm.telegram_chat_id, 1)
        self.assertEqual(tm.telegram_message_id, 12345)
        self.assertEqual(tm.telegram_user_id, 100)
        self.assertEqual(tm.telegram_username, "test_user")

        reg = Registration.objects.get()
        self.assertEqual(reg.telegram_message, tm)

    def test_case_insensitive_keyword(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        for text in ["РЕГА 1 клан", "Регистрация 1 клан", "РеГа 1 клан"]:
            with self.subTest(text=text):
                Registration.objects.all().delete()
                TelegramMessage.objects.all().delete()
                result = self._process(text=text, message_id=Registration.objects.count() + 1)
                self.assertEqual(result.status, ProcessResultStatus.REGISTRATION_CREATED)


@override_settings(ADMIN_TELEGRAM_CHAT_IDS="", TELEGRAM_BOT_TOKEN="")
class ProcessRegistrationEditTests(TestCase):
    def setUp(self):
        RegistrationRate.objects.all().delete()
        RegistrationRate.objects.create(
            start_time=time(0, 0),
            end_time=time(23, 59),
            rate_kk=Decimal("10.00"),
            active=True,
            order=0,
        )

    def _make_existing_message(self, user_id=100, status=TelegramMessage.Status.ERROR):
        tm = TelegramMessage.objects.create(
            telegram_chat_id=1,
            telegram_message_id=1,
            telegram_user_id=user_id,
            telegram_username="test_user",
            text="рега 1 клан",
            message_date=timezone.now(),
            status=status,
        )
        return tm

    def _process_edit(
        self,
        text="рега 2 кланами атака форта",
        message_id=1,
        user_id=100,
        username="test_user",
        has_photo=True,
        photo_file_id="photo123",
        message_thread_id=None,
        message_date=None,
    ):
        if message_date is None:
            message_date = timezone.make_aware(datetime(2024, 1, 15, 12, 0))
        return process_registration_edit(
            chat_id=1,
            message_id=message_id,
            user_id=user_id,
            username=username,
            text=text,
            message_date=message_date,
            has_photo=has_photo,
            photo_file_id=photo_file_id,
            message_thread_id=message_thread_id,
        )

    def test_edit_on_error_reprocesses_and_creates_registration(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        self._make_existing_message(status=TelegramMessage.Status.ERROR)

        result = self._process_edit(text="рега 2 кланами атака форта")

        self.assertEqual(result.status, ProcessResultStatus.REGISTRATION_CREATED)
        self.assertEqual(Registration.objects.count(), 1)
        reg = Registration.objects.get()
        self.assertEqual(reg.clans_count, 2)
        self.assertEqual(reg.description, "атака форта")
        self.assertEqual(ProcessingError.objects.count(), 0)

    def test_edit_on_processed_is_ignored(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        tm = self._make_existing_message(status=TelegramMessage.Status.PROCESSED)
        Registration.objects.create(
            player=Player.objects.get(),
            telegram_message=tm,
            clans_count=1,
            payment_kk=Decimal("10.00"),
            description="",
            photo_file_id="old",
            registered_at=timezone.now(),
        )

        result = self._process_edit(text="рега 5 кланов новое")

        self.assertEqual(result.status, ProcessResultStatus.EDIT_IGNORED)
        self.assertEqual(Registration.objects.count(), 1)
        reg = Registration.objects.get()
        self.assertEqual(reg.clans_count, 1)  # unchanged

    def test_edit_without_existing_message_processes_as_new(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        result = self._process_edit(message_id=999)

        self.assertEqual(result.status, ProcessResultStatus.REGISTRATION_CREATED)
        self.assertEqual(TelegramMessage.objects.count(), 1)
        self.assertEqual(Registration.objects.count(), 1)

    def test_edit_with_invalid_text_updates_error(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        self._make_existing_message(status=TelegramMessage.Status.ERROR)
        old_error = ProcessingError.objects.create(
            telegram_message=TelegramMessage.objects.get(),
            reason="registration_missing_clans_count",
            status=ProcessingError.Status.NEW,
        )

        result = self._process_edit(text="рега ноль кланов")

        self.assertEqual(result.status, ProcessResultStatus.PROCESSING_ERROR)
        self.assertEqual(Registration.objects.count(), 0)
        error = ProcessingError.objects.get()
        self.assertEqual(error.reason, "registration_invalid_clans_count")
        self.assertNotEqual(error.pk, old_error.pk)

    def test_edit_requires_photo(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        self._make_existing_message(status=TelegramMessage.Status.ERROR)

        result = self._process_edit(has_photo=False, photo_file_id=None)

        self.assertEqual(result.status, ProcessResultStatus.VALIDATION_ERROR)
        self.assertEqual(Registration.objects.count(), 0)

    def test_edit_requires_registered_user(self):
        self._make_existing_message(user_id=999, status=TelegramMessage.Status.ERROR)

        result = self._process_edit(user_id=999)

        self.assertEqual(result.status, ProcessResultStatus.VALIDATION_ERROR)
        self.assertEqual(Registration.objects.count(), 0)


@override_settings(ADMIN_TELEGRAM_CHAT_IDS="", TELEGRAM_BOT_TOKEN="")
class RegistrationRateCalculationTests(TestCase):
    """Tests for registration rate calculations."""

    def setUp(self):
        RegistrationRate.objects.all().delete()

    def test_single_rate_all_day(self):
        RegistrationRate.objects.create(
            start_time=time(0, 0),
            end_time=time(23, 59),
            rate_kk=Decimal("10.00"),
            active=True,
        )
        from core.services.rates import registration_payment_kk
        payment = registration_payment_kk(time(12, 0), 3)
        self.assertEqual(payment, Decimal("30.00"))

    def test_rate_wraps_midnight(self):
        RegistrationRate.objects.create(
            start_time=time(22, 0),
            end_time=time(6, 0),
            rate_kk=Decimal("15.00"),
            active=True,
        )
        from core.services.rates import registration_payment_kk
        # 23:00 is within 22:00-06:00
        payment = registration_payment_kk(time(23, 0), 2)
        self.assertEqual(payment, Decimal("30.00"))
        # 12:00 is outside
        payment = registration_payment_kk(time(12, 0), 2)
        self.assertEqual(payment, Decimal("0.00"))

    def test_multiple_rates_priority_by_order(self):
        RegistrationRate.objects.create(
            start_time=time(0, 0),
            end_time=time(23, 59),
            rate_kk=Decimal("5.00"),
            active=True,
            order=1,
        )
        RegistrationRate.objects.create(
            start_time=time(10, 0),
            end_time=time(14, 0),
            rate_kk=Decimal("20.00"),
            active=True,
            order=0,  # higher priority
        )
        from core.services.rates import registration_payment_kk
        # 12:00 should use order=0 rate (20.00)
        payment = registration_payment_kk(time(12, 0), 1)
        self.assertEqual(payment, Decimal("20.00"))
        # 16:00 should use order=1 rate (5.00)
        payment = registration_payment_kk(time(16, 0), 1)
        self.assertEqual(payment, Decimal("5.00"))

    def test_no_active_rate_returns_zero(self):
        RegistrationRate.objects.create(
            start_time=time(0, 0),
            end_time=time(23, 59),
            rate_kk=Decimal("10.00"),
            active=False,  # inactive
        )
        from core.services.rates import registration_payment_kk
        payment = registration_payment_kk(time(12, 0), 5)
        self.assertEqual(payment, Decimal("0.00"))