"""Management command to send scheduled messages."""
import logging

from django.core.management.base import BaseCommand

from core.services.messaging_service import MessagingError, send_scheduled_message
from core.services.scheduling_service import due_schedules, release_lock, try_acquire_lock

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Send all due scheduled messages. Idempotent via PostgreSQL advisory lock."

    def handle(self, *args, **options):
        # Try to acquire advisory lock
        if not try_acquire_lock():
            logger.info("Another send_scheduled_messages process is running; exiting.")
            self.stdout.write("Another instance is running; exiting.")
            return

        try:
            now = None  # Will use _now_msk() inside due_schedules
            schedules = due_schedules(now)

            if not schedules:
                logger.info("No due scheduled messages.")
                self.stdout.write("No due scheduled messages.")
                return

            for schedule in schedules:
                try:
                    send_scheduled_message(schedule)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Sent scheduled message #{schedule.pk} '{schedule.name}'"
                        )
                    )
                except MessagingError as exc:
                    logger.error(
                        "Failed to send scheduled message schedule_id=%s: %s",
                        schedule.pk,
                        exc,
                    )
                    self.stdout.write(
                        self.style.ERROR(
                            f"Failed to send scheduled message #{schedule.pk} '{schedule.name}': {exc}"
                        )
                    )
                except Exception as exc:
                    logger.exception(
                        "Unexpected error sending scheduled message schedule_id=%s",
                        schedule.pk,
                    )
                    self.stdout.write(
                        self.style.ERROR(
                            f"Unexpected error sending scheduled message #{schedule.pk} '{schedule.name}': {exc}"
                        )
                    )

        finally:
            release_lock()