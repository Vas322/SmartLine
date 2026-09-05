"""Run the Django dev server together with the Telegram bot and scheduler."""
import threading
import time
import logging

from django.conf import settings
from django.contrib.staticfiles.management.commands.runserver import (
    Command as StaticRunserverCommand,
)
from telegram_bot.polling import run_poll_loop

logger = logging.getLogger(__name__)

SCHEDULER_INTERVAL_SECONDS = 60


def _scheduler_loop() -> None:
    """Background loop that checks for due scheduled messages every 60 seconds."""
    from core.services.scheduling_service import run_due_schedules

    logger.info("Scheduler thread started (checking every %ds).", SCHEDULER_INTERVAL_SECONDS)
    while True:
        try:
            run_due_schedules()
        except Exception:
            logger.exception("Unexpected error in scheduler loop")
        time.sleep(SCHEDULER_INTERVAL_SECONDS)


class Command(StaticRunserverCommand):
    help = "Run the Django dev server, Telegram bot and scheduler (all in one process)."

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

        # Scheduler thread: checks due_schedules() and sends each one.
        scheduler_thread = threading.Thread(
            target=_scheduler_loop, name="scheduler", daemon=True
        )
        scheduler_thread.start()
        logger.info("Scheduler thread '%s' started.", scheduler_thread.name)

        super().handle(*args, **options)
