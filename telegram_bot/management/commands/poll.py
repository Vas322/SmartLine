"""Run the Telegram bot in long-polling mode."""
import logging

from django.core.management.base import BaseCommand

from telegram_bot.polling import run_poll_loop

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Smartline Telegram bot in long-polling mode"

    def handle(self, *args, **options) -> None:
        self.stdout.write("Telegram bot polling started. Press Ctrl+C to stop.")
        run_poll_loop()
