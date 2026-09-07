"""Tests for welcome routing (new_chat_members / left_chat_member) in the handler."""
from unittest import mock

from django.test import SimpleTestCase

from telegram_bot.handler import handle_update


class WelcomeHandlerRoutingTests(SimpleTestCase):
    """new_chat_members / left_chat_member events must route to welcome_service.

    Ordinary text messages must NOT be routed to welcome_service (regression).
    """

    @mock.patch("telegram_bot.handler.welcome_service.handle_new_chat_members")
    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_new_chat_members_routes_to_welcome_service(self, mock_process, mock_welcome):
        members = [{"id": 1, "username": "newbie"}]
        update = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "chat": {"id": 1000},
                "date": 1750000000,
                "message_thread_id": 12,
                "new_chat_members": members,
            },
        }
        handle_update(update)

        mock_welcome.assert_called_once()
        kwargs = mock_welcome.call_args.kwargs
        self.assertEqual(kwargs["chat_id"], 1000)
        self.assertEqual(kwargs["message_id"], 10)
        self.assertEqual(kwargs["new_members"], members)
        self.assertEqual(kwargs["message_thread_id"], 12)
        mock_process.assert_not_called()

    @mock.patch("telegram_bot.handler.welcome_service.handle_new_chat_members")
    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_new_chat_members_without_thread_id(self, mock_process, mock_welcome):
        update = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "chat": {"id": 1000},
                "date": 1750000000,
                "new_chat_members": [{"id": 1}],
            },
        }
        handle_update(update)
        self.assertIsNone(mock_welcome.call_args.kwargs["message_thread_id"])
        mock_process.assert_not_called()

    @mock.patch("telegram_bot.handler.welcome_service.handle_left_chat_member")
    @mock.patch("telegram_bot.handler.process_telegram_message")
    def test_left_chat_member_routes_to_welcome_service(self, mock_process, mock_welcome):
        update = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "chat": {"id": 1000},
                "date": 1750000000,
                "left_chat_member": {"id": 500, "username": "gone"},
            },
        }
        handle_update(update)

        mock_welcome.assert_called_once_with(user_id=500)
        mock_process.assert_not_called()

    @mock.patch("telegram_bot.handler.welcome_service.handle_left_chat_member")
    @mock.patch("telegram_bot.handler.welcome_service.handle_new_chat_members")
    @mock.patch(
        "telegram_bot.handler.process_telegram_message",
        return_value=mock.Mock(status=mock.Mock(value="OK")),
    )
    def test_regular_message_not_routed_to_welcome(self, mock_process, mock_new, mock_left):
        update = {
            "update_id": 1,
            "message": {
                "message_id": 10,
                "chat": {"id": 1000},
                "date": 1750000000,
                "from": {"id": 500, "username": "swettka"},
                "text": "+1 | деф | Swettka | Первая волна",
            },
        }
        handle_update(update)

        mock_process.assert_called_once()
        mock_new.assert_not_called()
        mock_left.assert_not_called()
