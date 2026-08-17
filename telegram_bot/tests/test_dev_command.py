"""Tests for the dev command and the shared polling loop."""
from unittest import mock

from django.test import TestCase, override_settings

from telegram_bot import polling


class PollingLoopTests(TestCase):
    def test_run_poll_loop_processes_update_and_stops_on_interrupt(self):
        update = {"update_id": 5, "message": {"message_id": 5}}
        calls = []

        def fake_get_updates(offset=None, timeout=30):
            if not calls:
                calls.append(1)
                return [update]
            raise KeyboardInterrupt()

        with mock.patch.object(
            polling.TelegramBot, "get_updates", side_effect=fake_get_updates
        ), mock.patch.object(
            polling, "handle_update", wraps=polling.handle_update
        ) as spy:
            with self.assertRaises(KeyboardInterrupt):
                polling.run_poll_loop()
            self.assertEqual(calls, [1])
            spy.assert_called_once_with(update)

    def test_run_poll_loop_survives_update_exception(self):
        update = {"update_id": 7, "message": {"message_id": 7}}
        calls = []

        def fake_get_updates(offset=None, timeout=30):
            if not calls:
                calls.append(1)
                return [update]
            raise KeyboardInterrupt()

        with mock.patch.object(
            polling.TelegramBot, "get_updates", side_effect=fake_get_updates
        ), mock.patch.object(
            polling, "handle_update", side_effect=RuntimeError("boom")
        ):
            with self.assertRaises(KeyboardInterrupt):
                polling.run_poll_loop()


class DevCommandTests(TestCase):
    def test_dev_command_subclasses_static_runserver(self):
        from django.contrib.staticfiles.management.commands.runserver import (
            Command as StaticRunserverCommand,
        )
        from telegram_bot.management.commands.dev import Command as DevCommand

        self.assertTrue(issubclass(DevCommand, StaticRunserverCommand))

    @override_settings(TELEGRAM_BOT_TOKEN="")
    @mock.patch("threading.Thread")
    @mock.patch(
        "django.contrib.staticfiles.management.commands.runserver.Command.handle"
    )
    def test_dev_does_not_start_bot_without_token(self, mock_srv, mock_thread):
        from telegram_bot.management.commands.dev import Command

        Command().handle()
        mock_thread.assert_not_called()
        mock_srv.assert_called_once()

    @override_settings(TELEGRAM_BOT_TOKEN="123:abc")
    @mock.patch("threading.Thread")
    @mock.patch(
        "django.contrib.staticfiles.management.commands.runserver.Command.handle"
    )
    def test_dev_starts_bot_with_token(self, mock_srv, mock_thread):
        from telegram_bot.management.commands.dev import Command

        Command().handle()
        mock_thread.assert_called_once()
        mock_srv.assert_called_once()
