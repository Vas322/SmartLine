"""Tests for the activity processing service."""
from datetime import time
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import Activity, CastRate, Player, ProcessingError, Rate, TelegramMessage
from core.services.activity_service import (
    ProcessResultStatus,
    process_telegram_edit,
    process_telegram_message,
)


def _process(text: str, chat_id: int = 1, message_id: int = 1):
    return process_telegram_message(
        chat_id=chat_id,
        message_id=message_id,
        user_id=100,
        username="test_user",
        text=text,
        message_date=timezone.now(),
    )


def _process_edit(text: str, chat_id: int = 1, message_id: int = 1):
    return process_telegram_edit(
        chat_id=chat_id,
        message_id=message_id,
        user_id=100,
        username="test_user",
        text=text,
        message_date=timezone.now(),
    )


@override_settings(ADMIN_TELEGRAM_CHAT_IDS="", TELEGRAM_BOT_TOKEN="")
class ProcessTelegramMessageTests(TestCase):
    def test_regular_message_is_ignored(self):
        result = _process("Сегодня идём на деф")
        self.assertEqual(result.status, ProcessResultStatus.IGNORED)
        self.assertEqual(TelegramMessage.objects.count(), 0)
        self.assertEqual(Activity.objects.count(), 0)

    def test_valid_message_creates_activity(self):
        Player.objects.create(nickname="Swettka")
        result = _process("+1 | деф | Swettka | 11.56 | Первая волна")

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        activity = Activity.objects.get()
        self.assertEqual(result.activities[0], activity)
        self.assertEqual(activity.amount, Decimal("1"))
        self.assertEqual(activity.activity_type, "DEF")
        self.assertEqual(activity.player.nickname, "Swettka")
        self.assertEqual(activity.description, "Первая волна")
        self.assertEqual(
            activity.telegram_message,
            result.telegram_message,
        )
        self.assertEqual(
            result.telegram_message.status,
            TelegramMessage.Status.PROCESSED,
        )

    def test_duplicate_message_returns_duplicate(self):
        Player.objects.create(nickname="Swettka")
        first = _process("+1 | деф | Swettka | 11.56 | Первая волна")
        self.assertEqual(first.status, ProcessResultStatus.ACTIVITY_CREATED)

        second = _process("+1 | деф | Swettka | 11.56 | Первая волна")
        self.assertEqual(second.status, ProcessResultStatus.DUPLICATE)
        self.assertEqual(Activity.objects.count(), 1)

    def test_different_messages_create_two_activities(self):
        Player.objects.create(nickname="Swettka")
        _process("+1 | деф | Swettka | 11.56 | Первая волна", message_id=1)
        _process("+2 | фарм | Swettka | 11.56 | Фарм", message_id=2)
        self.assertEqual(Activity.objects.count(), 2)

    def test_invalid_amount_creates_processing_error(self):
        Player.objects.create(nickname="Swettka")
        result = _process("+abc | деф | Swettka | 11.56 | описание")

        self.assertEqual(result.status, ProcessResultStatus.PROCESSING_ERROR)
        self.assertEqual(Activity.objects.count(), 0)
        error = ProcessingError.objects.get()
        self.assertEqual(error.reason, "invalid_amount")
        self.assertEqual(error.status, ProcessingError.Status.NEW)
        self.assertEqual(
            result.telegram_message.status,
            TelegramMessage.Status.ERROR,
        )

    def test_unknown_player_is_auto_created(self):
        result = _process("+1 | деф | Newbie | 11.56 | описание")

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        player = Player.objects.get(nickname="Newbie")
        activity = Activity.objects.get()
        self.assertEqual(activity.player, player)

    def test_unknown_player_without_user_id_is_auto_created(self):
        result = process_telegram_message(
            chat_id=1,
            message_id=1,
            text="+1 | деф | Newbie | 11.56 | описание",
            message_date=timezone.now(),
        )
        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        player = Player.objects.get(nickname="Newbie")
        self.assertEqual(player.nickname, "Newbie")

    def test_nicknames_are_case_insensitive_but_first_spelling_kept(self):
        _process("+1 | деф | pocomaxa | 11.56 | Первая", message_id=1)
        result = _process("+2 | деф | POCOMAXA | 11.56 | Вторая", message_id=2)

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        self.assertEqual(Player.objects.count(), 1)
        player = Player.objects.get()
        self.assertEqual(player.nickname, "pocomaxa")
        self.assertEqual(Activity.objects.count(), 2)

    def test_nickname_is_resolved_by_nickname_not_sender(self):
        """Existing player by nickname is used even if user_id differs (no binding yet)."""
        Player.objects.create(nickname="Swettka")
        result = process_telegram_message(
            chat_id=1,
            message_id=1,
            user_id=999,
            username="someone_else",
            text="+1 | деф | Swettka | 11.56 | Первая волна",
            message_date=timezone.now(),
        )

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        self.assertEqual(Player.objects.filter(nickname="Swettka").count(), 1)
        player = Player.objects.get(nickname="Swettka")
        # Since player had no telegram_user_id, it gets bound to user_id=999
        self.assertEqual(player.telegram_user_id, 999)

    def test_same_user_can_use_own_nickname_repeatedly(self):
        _process("+1 | деф | Swettka | 11.56 | Первая", message_id=1)
        result = _process("+2 | деф | Swettka | 11.56 | Вторая", message_id=2)

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        self.assertEqual(Player.objects.filter(nickname="Swettka").count(), 1)
        self.assertEqual(Activity.objects.count(), 2)

    def test_def_is_paid(self):
        player = Player.objects.create(nickname="Swettka")
        _process("+1.5 | деф | Swettka | 11.56 | Деф")
        activity = Activity.objects.get(player=player)
        self.assertEqual(activity.amount, Decimal("1.5"))
        self.assertEqual(activity.wave_start_time, time(11, 56))
        self.assertEqual(activity.payment_kk, Decimal("112.50"))

    def test_farm_is_not_paid(self):
        Player.objects.create(nickname="Swettka")
        _process("+2 | фарм | Swettka | 11.56 | Фарм")
        activity = Activity.objects.get()
        self.assertEqual(activity.activity_type, "FARM")
        self.assertEqual(activity.amount, Decimal("2"))
        self.assertEqual(activity.wave_start_time, time(11, 56))
        self.assertEqual(activity.payment_kk, Decimal("0"))

    def test_decimal_sum_without_float_errors(self):
        Player.objects.create(nickname="Swettka")
        _process("+0.3 | деф | Swettka | 11.56 | Первая", message_id=1)
        _process("+0.5 | деф | Swettka | 11.56 | Вторая", message_id=2)
        _process("+0.2 | деф | Swettka | 11.56 | Третья", message_id=3)

        total = sum(
            (a.amount for a in Activity.objects.all()),
            Decimal("0"),
        )
        self.assertEqual(total, Decimal("1.0"))

    # --- new binding logic tests ---

    def test_resolve_by_user_id_takes_precedence(self):
        """Player with telegram_user_id=100 is resolved by user_id even if nick differs."""
        Player.objects.create(nickname="OldNick", telegram_user_id=100)
        result = _process("+1 | деф | Swettka | 11.56 | Первая", message_id=1)

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        self.assertEqual(Player.objects.count(), 1)
        player = Player.objects.get()
        self.assertEqual(player.nickname, "Swettka")  # nickname adopted
        self.assertEqual(player.telegram_user_id, 100)

    def test_nick_already_bound(self):
        """Player with telegram_user_id=100 cannot be claimed by user_id=200."""
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        result = process_telegram_message(
            chat_id=1,
            message_id=1,
            user_id=200,
            username="user_b",
            text="+1 | деф | Swettka | 11.56 | Первая",
            message_date=timezone.now(),
        )

        self.assertEqual(result.status, ProcessResultStatus.PROCESSING_ERROR)
        error = ProcessingError.objects.get()
        self.assertEqual(error.reason, "nick_already_bound")
        self.assertEqual(Activity.objects.count(), 0)

    def test_auto_create_binds_user_id(self):
        """New player gets telegram_user_id bound on creation."""
        result = _process("+1 | деф | Newbie | 11.56 | описание", message_id=1)

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        player = Player.objects.get(nickname="Newbie")
        self.assertEqual(player.telegram_user_id, 100)

    def test_no_duplicate_player_for_same_user_id(self):
        """Two calls with same user_id but different nickname spelling -> one player."""
        _process("+1 | деф | Swettka | 11.56 | Первая", message_id=1)
        result = _process("+2 | деф | Swettkaa | 11.56 | Вторая", message_id=2)

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        self.assertEqual(Player.objects.count(), 1)
        player = Player.objects.get()
        self.assertEqual(player.nickname, "Swettkaa")  # latest spelling adopted
        self.assertEqual(player.telegram_user_id, 100)
        self.assertEqual(Activity.objects.count(), 2)

    @patch("core.services.activity_service.notify_group_reply")
    def test_nick_change_notifies_group(self, mock_notify):
        """Nick change triggers group notification."""
        Player.objects.create(nickname="Swettka", telegram_user_id=100)
        _process("+1 | деф | Swettkaa | 11.56 | Вторая", message_id=1)

        self.assertEqual(Player.objects.count(), 1)
        player = Player.objects.get()
        self.assertEqual(player.nickname, "Swettkaa")
        mock_notify.assert_called_once()
        args, _ = mock_notify.call_args
        self.assertIn("Ник изменён: Swettka → Swettkaa", args[1])

    @patch("core.services.activity_service.notify_group_reply")
    def test_new_player_created_notifies_group(self, mock_notify):
        """Auto-created player triggers group notification."""
        result = _process("+1 | деф | Pocomaxa | 11.56 | Первая", message_id=1)

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        player = Player.objects.get()
        self.assertEqual(player.nickname, "Pocomaxa")
        mock_notify.assert_called_once()
        args, _ = mock_notify.call_args
        self.assertIn(
            "Зарегистрирован новый игрок! На Pocomaxa будет приходить оплата!",
            args[1],
        )


@override_settings(ADMIN_TELEGRAM_CHAT_IDS="", TELEGRAM_BOT_TOKEN="")
class ProcessTelegramEditTests(TestCase):
    """Tests for re-processing edited Telegram messages."""

    def test_edit_on_error_reprocesses_and_creates_activity(self):
        first = _process("+abc | деф | Swettka | 11.56 | описание")
        self.assertEqual(first.status, ProcessResultStatus.PROCESSING_ERROR)
        self.assertEqual(ProcessingError.objects.count(), 1)

        result = _process_edit("+1 | деф | Swettka | 11.56 | Первая волна")

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        self.assertEqual(Activity.objects.count(), 1)
        self.assertEqual(ProcessingError.objects.count(), 0)
        activity = Activity.objects.get()
        self.assertEqual(activity.player.nickname, "Swettka")
        self.assertEqual(activity.amount, Decimal("1"))
        self.assertEqual(activity.wave_start_time, time(11, 56))
        self.assertEqual(activity.payment_kk, Decimal("75.00"))
        self.assertEqual(
            result.telegram_message.status,
            TelegramMessage.Status.PROCESSED,
        )

    def test_edit_on_error_with_invalid_text_updates_error(self):
        first = _process("+abc | деф | Swettka | 11.56 | описание")
        self.assertEqual(first.status, ProcessResultStatus.PROCESSING_ERROR)
        old_error = ProcessingError.objects.get()
        self.assertEqual(old_error.reason, "invalid_amount")

        result = _process_edit("+1 | неизвестный_тип | Swettka | 11.56 | описание")

        self.assertEqual(result.status, ProcessResultStatus.PROCESSING_ERROR)
        self.assertEqual(Activity.objects.count(), 0)
        error = ProcessingError.objects.get()
        self.assertEqual(error.reason, "unknown_activity_type")
        self.assertNotEqual(error.pk, old_error.pk)
        self.assertEqual(
            result.telegram_message.status,
            TelegramMessage.Status.ERROR,
        )

    def test_edit_on_processed_message_is_ignored(self):
        Player.objects.create(nickname="Swettka")
        first = _process("+1 | деф | Swettka | 11.56 | Первая волна")
        self.assertEqual(first.status, ProcessResultStatus.ACTIVITY_CREATED)

        result = _process_edit("+2 | фарм | Swettka | 11.56 | Вторая волна")

        self.assertEqual(result.status, ProcessResultStatus.EDIT_IGNORED)
        self.assertEqual(Activity.objects.count(), 1)
        activity = Activity.objects.get()
        self.assertEqual(activity.amount, Decimal("1"))
        self.assertEqual(activity.activity_type, "DEF")

    def test_edit_without_existing_message_processes_as_new(self):
        Player.objects.create(nickname="Swettka")
        result = _process_edit("+1 | деф | Swettka | 11.56 | Первая волна")

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        self.assertEqual(TelegramMessage.objects.count(), 1)
        self.assertEqual(Activity.objects.count(), 1)

    def test_edit_of_non_activity_text_is_ignored(self):
        _process("+abc | деф | Swettka | 11.56 | описание")

        result = _process_edit("просто текст без плюса")

        self.assertEqual(result.status, ProcessResultStatus.IGNORED)
        self.assertEqual(ProcessingError.objects.count(), 1)
        self.assertEqual(Activity.objects.count(), 0)


@override_settings(ADMIN_TELEGRAM_CHAT_IDS="", TELEGRAM_BOT_TOKEN="")
class CastPaymentTests(TestCase):
    """CAST (каст/перекаст) is paid from CastRate; payment is the SUM of
    paid components with no multiplier."""

    def setUp(self):
        Rate.objects.all().delete()
        CastRate.objects.all().delete()
        Rate.objects.create(
            start_time=time(8, 1),
            end_time=time(16, 0),
            rate_kk=Decimal("75"),
            order=2,
        )
        CastRate.objects.create(
            start_time=time(8, 1),
            end_time=time(16, 0),
            rate_kk=Decimal("75"),
            order=2,
        )

    def test_def_only_pays_def_rate(self):
        Player.objects.create(nickname="Swettka")
        _process("+1 | деф | Swettka | 11.56")
        activity = Activity.objects.get()
        self.assertEqual(activity.activity_type, "DEF")
        self.assertFalse(activity.has_cast)
        self.assertEqual(activity.payment_kk, Decimal("75.00"))

    def test_def_plus_cast_payment_is_sum(self):
        Player.objects.create(nickname="Swettka")
        _process("+1 | деф+каст | Swettka | 11.56 | Первая волна")
        activity = Activity.objects.get()
        self.assertEqual(activity.activity_type, "DEF")
        self.assertTrue(activity.has_cast)
        self.assertEqual(activity.payment_kk, Decimal("150.00"))

    def test_standalone_cast_payment_from_cast_rate(self):
        Player.objects.create(nickname="Swettka")
        _process("+0,3 | каст | Swettka | 11.56 | Первая волна")
        activity = Activity.objects.get()
        self.assertEqual(activity.activity_type, "CAST")
        self.assertTrue(activity.has_cast)
        self.assertEqual(activity.payment_kk, Decimal("22.50"))

    def test_farm_plus_cast_pays_only_cast(self):
        Player.objects.create(nickname="presli")
        _process("+1 | фарм+каст | presli | 11:56")
        activity = Activity.objects.get()
        self.assertEqual(activity.activity_type, "FARM")
        self.assertTrue(activity.has_cast)
        self.assertEqual(activity.payment_kk, Decimal("75.00"))

    def test_def_plus_cast_prorated_amount(self):
        Player.objects.create(nickname="presli")
        _process("+0,7 | деф+каст | presli | 11:56")
        activity = Activity.objects.get()
        self.assertEqual(activity.activity_type, "DEF")
        self.assertTrue(activity.has_cast)
        self.assertEqual(activity.payment_kk, Decimal("105.00"))

    def test_farm_only_is_not_paid(self):
        Player.objects.create(nickname="Swettka")
        _process("+1 | фарм | Swettka | 11:56")
        activity = Activity.objects.get()
        self.assertEqual(activity.activity_type, "FARM")
        self.assertFalse(activity.has_cast)
        self.assertEqual(activity.payment_kk, Decimal("0"))

    def test_recast_is_paid_like_cast(self):
        Player.objects.create(nickname="Swettka")
        _process("+1 | перекаст | Swettka | 11.56")
        activity = Activity.objects.get()
        self.assertEqual(activity.activity_type, "CAST")
        self.assertTrue(activity.has_cast)
        self.assertEqual(activity.payment_kk, Decimal("75.00"))

    def test_cast_via_edit_path_is_paid(self):
        Player.objects.create(nickname="Swettka")
        first = _process("+abc | деф | Swettka | 11.56 | описание")
        self.assertEqual(first.status, ProcessResultStatus.PROCESSING_ERROR)

        result = _process_edit("+1 | каст | Swettka | 11.56")
        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        activity = Activity.objects.get()
        self.assertEqual(activity.activity_type, "CAST")
        self.assertTrue(activity.has_cast)
        self.assertEqual(activity.payment_kk, Decimal("75.00"))


class PlayerDeletionTests(TestCase):
    """Tests for deleting/deactivating players with activity history."""

    def setUp(self):
        self.player = Player.objects.create(nickname="Swettka")
        self.message = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=20,
            telegram_user_id=100,
            telegram_username="swettka",
            text="+1 | деф | Swettka | 11.56 | Первая волна",
            message_date=timezone.now(),
            status=TelegramMessage.Status.PROCESSED,
        )
        self.activity = Activity.objects.create(
            player=self.player,
            telegram_message=self.message,
            amount=Decimal("1"),
            activity_type=Activity.ActivityType.DEF,
            description="Первая волна",
        )

    def test_player_delete_cascades_activities(self):
        self.player.delete()

        self.assertEqual(Player.objects.count(), 0)
        self.assertEqual(Activity.objects.count(), 0)
        # TelegramMessage is not tied to Player, so the audit trail survives.
        self.assertEqual(TelegramMessage.objects.count(), 1)

    def test_player_deactivate_keeps_activities(self):
        self.player.is_active = False
        self.player.save()

        self.assertEqual(Player.objects.count(), 1)
        self.assertEqual(Activity.objects.count(), 1)
        self.assertFalse(Player.objects.get(pk=self.player.pk).is_active)

    def test_admin_can_delete_player_with_activities(self):
        User.objects.create_superuser(
            username="admin",
            password="test-password-123",
        )
        self.client.login(username="admin", password="test-password-123")

        url = f"/admin/core/player/{self.player.pk}/delete/"
        response = self.client.post(url, {"post": "yes"})

        self.assertNotEqual(response.status_code, 500)
        self.assertEqual(Player.objects.count(), 0)
        self.assertEqual(Activity.objects.count(), 0)