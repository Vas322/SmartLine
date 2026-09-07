"""Tests for the welcome service (greeting new Telegram group members)."""
from datetime import timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import OutgoingMessage, Player
from core.services import welcome_service


@override_settings(TELEGRAM_BOT_TOKEN="12345:TESTTOKEN")
class WelcomeServiceTests(TestCase):
    """Business logic of new_chat_members / left_chat_member handling."""

    def setUp(self):
        self.settings = welcome_service.get_welcome_settings()
        self.settings.welcome_text = "Добро пожаловать в клан!"
        self.settings.block_until = None
        self.settings.save()

    def _join(self, members, chat_id=1000, message_id=10):
        return welcome_service.handle_new_chat_members(
            chat_id=chat_id,
            message_id=message_id,
            new_members=members,
        )

    # ---------- Первый вход ----------

    @mock.patch(
        "telegram_bot.bot.TelegramBot.send_message",
        return_value={"result": {"message_id": 999}},
    )
    def test_first_join_creates_player_and_sends_welcome(self, mock_send):
        self._join([{"id": 111, "username": "newbie", "first_name": "New"}])

        player = Player.objects.get(telegram_user_id=111)
        self.assertIsNone(player.nickname)
        self.assertEqual(player.telegram_username, "newbie")
        self.assertTrue(player.is_active)

        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], 1000)
        self.assertEqual(kwargs["reply_to_message_id"], 10)
        self.assertIn("Добро пожаловать", kwargs["text"])

        outgoing = OutgoingMessage.objects.get()
        self.assertEqual(outgoing.source, OutgoingMessage.Source.WELCOME)
        self.assertEqual(outgoing.reply_to_message_id, 10)
        self.assertEqual(outgoing.status, OutgoingMessage.Status.SENT)

    @mock.patch(
        "telegram_bot.bot.TelegramBot.send_message",
        return_value={"result": {"message_id": 999}},
    )
    def test_missing_username_is_stored_as_empty(self, mock_send):
        self._join([{"id": 111}])
        player = Player.objects.get(telegram_user_id=111)
        self.assertEqual(player.telegram_username, "")

    # ---------- Повторный вход ----------

    @mock.patch(
        "telegram_bot.bot.TelegramBot.send_message",
        return_value={"result": {"message_id": 999}},
    )
    def test_second_join_does_not_create_player_or_send_welcome(self, mock_send):
        self._join([{"id": 111, "username": "newbie"}])
        mock_send.assert_called_once()
        mock_send.reset_mock()

        self._join([{"id": 111, "username": "newbie"}])

        self.assertEqual(Player.objects.filter(telegram_user_id=111).count(), 1)
        mock_send.assert_not_called()

    # ---------- left -> rejoin ----------

    @mock.patch(
        "telegram_bot.bot.TelegramBot.send_message",
        return_value={"result": {"message_id": 999}},
    )
    def test_left_then_rejoin_reactivates_without_welcome(self, mock_send):
        self._join([{"id": 111, "username": "newbie"}])
        player = Player.objects.get(telegram_user_id=111)
        created_at = player.created_at
        mock_send.reset_mock()

        welcome_service.handle_left_chat_member(user_id=111)
        player.refresh_from_db()
        self.assertFalse(player.is_active)

        self._join([{"id": 111, "username": "newbie"}])

        player.refresh_from_db()
        self.assertTrue(player.is_active)
        self.assertEqual(player.created_at, created_at)  # created_at не меняется
        mock_send.assert_not_called()

    # ---------- left_chat_member ----------

    def test_left_chat_member_deactivates_player(self):
        player = Player.objects.create(nickname="Swettka", telegram_user_id=111)
        welcome_service.handle_left_chat_member(user_id=111)
        player.refresh_from_db()
        self.assertFalse(player.is_active)

    def test_left_chat_member_without_player_does_not_fail(self):
        welcome_service.handle_left_chat_member(user_id=99999)
        self.assertEqual(Player.objects.count(), 0)

    # ---------- Массовый заход (анти-спам) ----------

    @mock.patch(
        "telegram_bot.bot.TelegramBot.send_message",
        return_value={"result": {"message_id": 999}},
    )
    def test_mass_join_blocks_welcome_and_creates_all_players(self, mock_send):
        members = [
            {"id": 1, "username": "u1"},
            {"id": 2, "username": "u2"},
            {"id": 3, "username": "u3"},
            {"id": 4, "username": "u4"},
        ]
        self._join(members)

        mock_send.assert_not_called()  # массовый заход — без приветствия
        self.assertEqual(Player.objects.count(), 4)  # игроки всё равно созданы

        self.settings.refresh_from_db()
        self.assertIsNotNone(self.settings.block_until)
        self.assertGreater(self.settings.block_until, timezone.now())

    # ---------- Блокировка ----------

    @mock.patch(
        "telegram_bot.bot.TelegramBot.send_message",
        return_value={"result": {"message_id": 999}},
    )
    def test_active_block_prevents_welcome_but_creates_player(self, mock_send):
        self.settings.block_until = timezone.now() + timedelta(minutes=30)
        self.settings.save()

        self._join([{"id": 111, "username": "newbie"}])

        mock_send.assert_not_called()
        self.assertEqual(Player.objects.filter(telegram_user_id=111).count(), 1)

    @mock.patch(
        "telegram_bot.bot.TelegramBot.send_message",
        return_value={"result": {"message_id": 999}},
    )
    def test_no_block_allows_welcome(self, mock_send):
        self._join([{"id": 111, "username": "newbie"}])
        mock_send.assert_called_once()

    # ---------- Пустой текст ----------

    @mock.patch(
        "telegram_bot.bot.TelegramBot.send_message",
        return_value={"result": {"message_id": 999}},
    )
    def test_empty_text_skips_welcome_but_creates_player(self, mock_send):
        self.settings.welcome_text = ""
        self.settings.save()

        self._join([{"id": 111, "username": "newbie"}])

        mock_send.assert_not_called()
        self.assertEqual(Player.objects.filter(telegram_user_id=111).count(), 1)

    # ---------- Уникальность telegram_user_id ----------

    @mock.patch(
        "telegram_bot.bot.TelegramBot.send_message",
        return_value={"result": {"message_id": 999}},
    )
    def test_existing_user_id_does_not_create_duplicate(self, mock_send):
        Player.objects.create(nickname="Existing", telegram_user_id=111)

        self._join([{"id": 111, "username": "newbie"}])

        self.assertEqual(Player.objects.filter(telegram_user_id=111).count(), 1)
        # существующий игрок не перезаписан и не активирован повторно (уже active)
        self.assertEqual(
            Player.objects.get(telegram_user_id=111).nickname,
            "Existing",
        )

    # ---------- reset_block_until ----------

    def test_reset_block_until_clears_block(self):
        self.settings.block_until = timezone.now() + timedelta(minutes=30)
        self.settings.save()

        welcome_service.reset_block_until()

        self.settings.refresh_from_db()
        self.assertIsNone(self.settings.block_until)
