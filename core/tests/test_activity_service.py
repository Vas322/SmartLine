"""Tests for the activity processing service."""
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import Activity, Player, ProcessingError, TelegramMessage
from core.services.activity_service import (
    ProcessResultStatus,
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


@override_settings(ADMIN_TELEGRAM_CHAT_IDS="", TELEGRAM_BOT_TOKEN="")
class ProcessTelegramMessageTests(TestCase):
    def test_regular_message_is_ignored(self):
        result = _process("Сегодня идём на деф")
        self.assertEqual(result.status, ProcessResultStatus.IGNORED)
        self.assertEqual(TelegramMessage.objects.count(), 0)
        self.assertEqual(Activity.objects.count(), 0)

    def test_valid_message_creates_activity(self):
        Player.objects.create(nickname="Swettka")
        result = _process("+1 | деф | Swettka | Первая волна")

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        activity = Activity.objects.get()
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
        first = _process("+1 | деф | Swettka | Первая волна")
        self.assertEqual(first.status, ProcessResultStatus.ACTIVITY_CREATED)

        second = _process("+1 | деф | Swettka | Первая волна")
        self.assertEqual(second.status, ProcessResultStatus.DUPLICATE)
        self.assertEqual(Activity.objects.count(), 1)

    def test_different_messages_create_two_activities(self):
        Player.objects.create(nickname="Swettka")
        _process("+1 | деф | Swettka | Первая волна", message_id=1)
        _process("+2 | фарм | Swettka | Фарм", message_id=2)
        self.assertEqual(Activity.objects.count(), 2)

    def test_invalid_amount_creates_processing_error(self):
        Player.objects.create(nickname="Swettka")
        result = _process("+abc | деф | Swettka | описание")

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
        result = _process("+1 | деф | Newbie | описание")

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        player = Player.objects.get(nickname="Newbie")
        self.assertEqual(player.telegram_user_id, 100)
        self.assertEqual(player.telegram_username, "test_user")
        activity = Activity.objects.get()
        self.assertEqual(activity.player, player)

    def test_unknown_player_without_user_id_is_auto_created_unbound(self):
        result = process_telegram_message(
            chat_id=1,
            message_id=1,
            text="+1 | деф | Newbie | описание",
            message_date=timezone.now(),
        )
        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        player = Player.objects.get(nickname="Newbie")
        self.assertIsNone(player.telegram_user_id)

    def test_existing_unbound_player_is_bound_to_first_sender(self):
        Player.objects.create(nickname="Swettka")
        result = _process("+1 | деф | Swettka | Первая волна")

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        player = Player.objects.get(nickname="Swettka")
        self.assertEqual(player.telegram_user_id, 100)

    def test_nicknames_are_case_insensitive_but_first_spelling_kept(self):
        _process("+1 | деф | pocomaxa | Первая", message_id=1)
        result = _process("+2 | деф | POCOMAXA | Вторая", message_id=2)

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        self.assertEqual(Player.objects.count(), 1)
        player = Player.objects.get()
        self.assertEqual(player.nickname, "pocomaxa")
        self.assertEqual(Activity.objects.count(), 2)

    def test_nickname_bound_to_another_user_is_rejected(self):
        Player.objects.create(nickname="Swettka", telegram_user_id=999)
        result = _process("+1 | деф | Swettka | Первая волна")

        self.assertEqual(result.status, ProcessResultStatus.PROCESSING_ERROR)
        self.assertEqual(Activity.objects.count(), 0)
        error = ProcessingError.objects.get()
        self.assertTrue(
            error.reason.startswith("nickname_registered_to_other_telegram")
        )

    def test_same_user_can_use_own_nickname_repeatedly(self):
        _process("+1 | деф | Swettka | Первая", message_id=1)
        result = _process("+2 | деф | Swettka | Вторая", message_id=2)

        self.assertEqual(result.status, ProcessResultStatus.ACTIVITY_CREATED)
        self.assertEqual(Player.objects.filter(nickname="Swettka").count(), 1)
        self.assertEqual(Activity.objects.count(), 2)

    def test_def_is_paid(self):
        player = Player.objects.create(nickname="Swettka")
        _process("+1.5 | деф | Swettka | Деф")
        activity = Activity.objects.get(player=player)
        self.assertEqual(activity.amount, Decimal("1.5"))

    def test_farm_is_not_paid(self):
        Player.objects.create(nickname="Swettka")
        _process("+2 | фарм | Swettka | Фарм")
        activity = Activity.objects.get()
        self.assertEqual(activity.activity_type, "FARM")
        self.assertEqual(activity.amount, Decimal("2"))

    def test_decimal_sum_without_float_errors(self):
        Player.objects.create(nickname="Swettka")
        _process("+0.3 | деф | Swettka | Первая", message_id=1)
        _process("+0.5 | деф | Swettka | Вторая", message_id=2)
        _process("+0.2 | деф | Swettka | Третья", message_id=3)

        total = sum(
            (a.amount for a in Activity.objects.all()),
            Decimal("0"),
        )
        self.assertEqual(total, Decimal("1.0"))


class PlayerDeletionTests(TestCase):
    """Tests for deleting/deactivating players with activity history."""

    def setUp(self):
        self.player = Player.objects.create(nickname="Swettka")
        self.message = TelegramMessage.objects.create(
            telegram_chat_id=10,
            telegram_message_id=20,
            telegram_user_id=100,
            telegram_username="swettka",
            text="+1 | деф | Swettka | Первая волна",
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
