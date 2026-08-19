"""Shared Telegram long-polling loop."""
import logging
import time

from telegram_bot.bot import TelegramBot
from telegram_bot.handler import handle_update

logger = logging.getLogger(__name__)


def run_poll_loop() -> None:
    """Run the Telegram long-polling loop forever, retrying on errors."""
    bot = TelegramBot()
    offset = None
    logger.info("Telegram bot polling started.")
    while True:
        try:
            updates = bot.get_updates(offset=offset)
            for update in updates:
                try:
                    handle_update(update)
                except Exception:
                    logger.exception("Error handling telegram update")
                    # Keep the failed update's offset so Telegram redelivers
                    # it (at-least-once); duplicates are blocked by DB unique
                    # constraint on chat_id + message_id.
                    break
                offset = update["update_id"] + 1
        except Exception as exc:
            logger.error("Telegram polling error: %s", exc)
            time.sleep(10)
