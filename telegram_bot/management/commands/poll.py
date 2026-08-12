"""Run the Telegram bot in long-polling mode."""
import logging
import time
from typing import Optional

from django.core.management.base import BaseCommand

from telegram_bot.bot import TelegramBot
from telegram_bot.handler import handle_update

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Smartline Telegram bot in long-polling mode"

    def handle(self, *args, **options) -> None:
        bot = TelegramBot()
        offset: Optional[int] = None
        self.stdout.write("Telegram bot polling started. Press Ctrl+C to stop.")
        while True:
            try:
                updates = bot.get_updates(offset=offset)
                for update in updates:
                    handle_update(update)
                    offset = update["update_id"] + 1
            except KeyboardInterrupt:
                self.stdout.write("Stopping Telegram bot polling.")
                break
            except Exception as exc:
                logger.error("Telegram polling error: %s", exc, exc_info=True)
                time.sleep(10)