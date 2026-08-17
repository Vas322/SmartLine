"""Run the Django dev server together with the Telegram bot."""
import threading
import logging

from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticRunserverCommand,
)
from telegram_bot.polling import run_poll_loop

logger = logging.getLogger(__name__)


class Command(StaticRunserverCommand):
    help = "Run the Django dev server and auto-start the Telegram bot."

    def handle(self, *args, **options):
        # Single process: disable the auto-reloader so exactly one bot thread
        # runs (the reloader would otherwise spawn a second process and cause
        # a duplicate-bot / HTTP 409 conflict).
        options["use_reloader"] = False

        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        if token:
            bot_thread = threading.Thread(
                target=run_poll_loop, name="telegram-bot", daemon=True
            )
            bot_thread.start()
            logger.info(
                "Telegram bot auto-started in background thread '%s'.",
                bot_thread.name,
            )
        else:
            logger.warning(
                "TELEGRAM_BOT_TOKEN is not set; Telegram bot not started."
            )

        super().handle(*args, **options)
