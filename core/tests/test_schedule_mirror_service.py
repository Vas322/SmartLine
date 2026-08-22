"""Tests for the schedule mirror service."""
from datetime import datetime
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone

from core.models import ScheduleMirror, TelegramMessage
from core.services import schedule_mirror_service
from telegram_bot.bot import TelegramAPIError


@override_settings(
    TELEGRAM_BOT_TOKEN="12345:TESTTOKEN",
    SCHEDULE_SOURCE_CHAT_ID=-5329088669,
    ALLIANCE_BOT_USERNAME="x5_fort_bot",
    CLAN_CHAT_ID=-1000000000,
)
class ScheduleMirrorServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="kl", password="test-password")
        TelegramMessage.objects.all().delete()
        ScheduleMirror.objects.all().delete()

    def _mock_bot(self):
        """Create a mock bot with all needed methods."""
        bot = mock.Mock(spec=schedule_mirror_service.TelegramBot)
        bot.copy_message = mock.Mock()
        bot.edit_message_text = mock.Mock()
        return bot

    @mock.patch("core.services.schedule_mirror_service._bot")
    def test_apply_to_target_creates_new_mirror(self, mock_bot_factory):
        """First message creates a new ScheduleMirror."""
        mock_bot = self._mock_bot()
        mock_bot.copy_message.return_value = {"ok": True, "result": {"message_id": 999}}
        mock_bot_factory.return_value = mock_bot

        mirror = schedule_mirror_service._apply_to_target(
            source_chat_id=-5329088669,
            source_message_id=100,
            text="Расписание на неделю",
            target_chat_id=-1000000000,
            alliance_bot_username="x5_fort_bot",
            label="Weekly",
            user=self.user,
        )

        self.assertIsInstance(mirror, ScheduleMirror)
        self.assertEqual(mirror.source_chat_id, -5329088669)
        self.assertEqual(mirror.source_message_id, 100)
        self.assertEqual(mirror.target_chat_id, -1000000000)
        self.assertEqual(mirror.target_message_id, 999)
        self.assertEqual(mirror.alliance_bot_username, "x5_fort_bot")
        self.assertEqual(mirror.label, "Weekly")
        self.assertEqual(mirror.last_text, "Расписание на неделю")
        self.assertTrue(mirror.is_active)
        self.assertEqual(mirror.created_by, self.user)

        mock_bot.copy_message.assert_called_once_with(
            chat_id=-1000000000,
            from_chat_id=-5329088669,
            from_message_id=100,
        )

    @mock.patch("core.services.schedule_mirror_service._bot")
    def test_apply_to_target_edits_existing_mirror_on_text_change(self, mock_bot_factory):
        """Same source message with different text updates the target message."""
        mock_bot = self._mock_bot()
        mock_bot_factory.return_value = mock_bot

        # Create existing mirror
        mirror = ScheduleMirror.objects.create(
            source_chat_id=-5329088669,
            source_message_id=100,
            target_chat_id=-1000000000,
            target_message_id=999,
            alliance_bot_username="x5_fort_bot",
            last_text="Старое расписание",
            is_active=True,
        )

        result = schedule_mirror_service._apply_to_target(
            source_chat_id=-5329088669,
            source_message_id=100,
            text="Новое расписание",
            target_chat_id=-1000000000,
            alliance_bot_username="x5_fort_bot",
            label="",
            user=None,
        )

        self.assertEqual(result.pk, mirror.pk)
        mock_bot.edit_message_text.assert_called_once_with(
            chat_id=-1000000000,
            message_id=999,
            text="Новое расписание",
        )
        mirror.refresh_from_db()
        self.assertEqual(mirror.last_text, "Новое расписание")

    @mock.patch("core.services.schedule_mirror_service._bot")
    def test_apply_to_target_same_text_does_not_edit(self, mock_bot_factory):
        """Same text does not trigger edit."""
        mock_bot = self._mock_bot()
        mock_bot_factory.return_value = mock_bot

        ScheduleMirror.objects.create(
            source_chat_id=-5329088669,
            source_message_id=100,
            target_chat_id=-1000000000,
            target_message_id=999,
            alliance_bot_username="x5_fort_bot",
            last_text="Текст расписания",
            is_active=True,
        )

        result = schedule_mirror_service._apply_to_target(
            source_chat_id=-5329088669,
            source_message_id=100,
            text="Текст расписания",
            target_chat_id=-1000000000,
            alliance_bot_username="x5_fort_bot",
            label="",
            user=None,
        )

        mock_bot.edit_message_text.assert_not_called()

    @mock.patch("core.services.schedule_mirror_service._bot")
    def test_apply_to_target_new_message_id_deactivates_old(self, mock_bot_factory):
        """New source_message_id for same source_chat deactivates old mirrors."""
        mock_bot = self._mock_bot()
        mock_bot.copy_message.return_value = {"ok": True, "result": {"message_id": 888}}
        mock_bot_factory.return_value = mock_bot

        # Create old active mirror
        old_mirror = ScheduleMirror.objects.create(
            source_chat_id=-5329088669,
            source_message_id=100,
            target_chat_id=-1000000000,
            target_message_id=999,
            alliance_bot_username="x5_fort_bot",
            last_text="Старое",
            is_active=True,
        )

        # Process new message_id
        result = schedule_mirror_service._apply_to_target(
            source_chat_id=-5329088669,
            source_message_id=200,
            text="Новое расписание",
            target_chat_id=-1000000000,
            alliance_bot_username="x5_fort_bot",
            label="",
            user=None,
        )

        old_mirror.refresh_from_db()
        self.assertFalse(old_mirror.is_active)
        self.assertEqual(result.source_message_id, 200)
        self.assertEqual(result.target_message_id, 888)
        self.assertTrue(result.is_active)

    @mock.patch("core.services.schedule_mirror_service._bot")
    def test_setup_mirror_fetches_text_and_applies(self, mock_bot_factory):
        """setup_mirror accepts text from admin and applies; copy_message returns only message_id."""
        mock_bot = self._mock_bot()
        # copy_message returns only message_id, NO text field
        mock_bot.copy_message.return_value = {"ok": True, "result": {"message_id": 777}}
        mock_bot_factory.return_value = mock_bot

        mirror = schedule_mirror_service.setup_mirror(
            source_chat_id=-5329088669,
            source_message_id=300,
            target_chat_id=-1000000000,
            alliance_bot_username="x5_fort_bot",
            label="Manual",
            user=self.user,
            text="ВСТАВЛЕННЫЙ ТЕКСТ",
        )

        self.assertEqual(mirror.last_text, "ВСТАВЛЕННЫЙ ТЕКСТ")
        mock_bot.copy_message.assert_called_once_with(
            chat_id=-1000000000,
            from_chat_id=-5329088669,
            from_message_id=300,
        )

    @mock.patch("core.services.schedule_mirror_service._bot")
    def test_setup_mirror_raises_on_copy_failure(self, mock_bot_factory):
        """setup_mirror raises ValueError if copy_message fails."""
        mock_bot = self._mock_bot()
        mock_bot.copy_message.side_effect = TelegramAPIError("Failed to copy")
        mock_bot_factory.return_value = mock_bot

        with self.assertRaises(ValueError) as ctx:
            schedule_mirror_service.setup_mirror(
                source_chat_id=-5329088669,
                source_message_id=300,
                target_chat_id=-1000000000,
                alliance_bot_username="x5_fort_bot",
                label="",
                user=self.user,
                text="Some text",
            )
        self.assertIn("Не удалось скопировать сообщение в группу клана", str(ctx.exception))

    @mock.patch("core.services.schedule_mirror_service._bot")
    def test_handle_source_message_uses_default_target(self, mock_bot_factory):
        """handle_source_message uses default target when None provided."""
        mock_bot = self._mock_bot()
        mock_bot.copy_message.return_value = {"ok": True, "result": {"message_id": 555}}
        mock_bot_factory.return_value = mock_bot

        result = schedule_mirror_service.handle_source_message(
            source_chat_id=-5329088669,
            source_message_id=400,
            text="Live message",
            alliance_bot_username="x5_fort_bot",
            is_edit=False,
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.target_chat_id, -1000000000)

    @mock.patch("core.services.schedule_mirror_service._bot")
    def test_reconcile_all_updates_changed_text(self, mock_bot_factory):
        """reconcile_all edits target messages using stored last_text (no get_message)."""
        mock_bot = self._mock_bot()
        mock_bot_factory.return_value = mock_bot

        ScheduleMirror.objects.create(
            source_chat_id=-5329088669,
            source_message_id=100,
            target_chat_id=-1000000000,
            target_message_id=999,
            alliance_bot_username="x5_fort_bot",
            last_text="Old text",
            is_active=True,
        )

        result = schedule_mirror_service.reconcile_all()

        mock_bot.edit_message_text.assert_called_once_with(
            chat_id=-1000000000,
            message_id=999,
            text="Old text",
        )
        self.assertEqual(result, {"updated": 1, "errors": 0})

    @mock.patch("core.services.schedule_mirror_service._bot")
    def test_reconcile_all_ignores_api_errors(self, mock_bot_factory):
        """reconcile_all continues on TelegramAPIError."""
        mock_bot = self._mock_bot()
        mock_bot.edit_message_text.side_effect = TelegramAPIError("Failed")
        mock_bot_factory.return_value = mock_bot

        ScheduleMirror.objects.create(
            source_chat_id=-5329088669,
            source_message_id=100,
            target_chat_id=-1000000000,
            target_message_id=999,
            alliance_bot_username="x5_fort_bot",
            last_text="Old text",
            is_active=True,
        )

        # Should not raise
        result = schedule_mirror_service.reconcile_all()
        self.assertEqual(result, {"updated": 0, "errors": 1})

    def test_get_current_text_returns_empty_when_no_active(self):
        """get_current_text returns empty string when no active mirror."""
        self.assertEqual(schedule_mirror_service.get_current_text(), "")

    def test_get_current_text_returns_active_mirror_text(self):
        """get_current_text returns last_text of active mirror."""
        ScheduleMirror.objects.create(
            source_chat_id=-5329088669,
            source_message_id=100,
            target_chat_id=-1000000000,
            target_message_id=999,
            last_text="Current schedule text",
            is_active=True,
        )
        self.assertEqual(schedule_mirror_service.get_current_text(), "Current schedule text")