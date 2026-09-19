"""Management command to send Epic RB Telegram notifications."""
import logging

from django.core.management.base import BaseCommand

from core.services.boss_notification_service import send_epic_boss_notification

logger = logging.getLogger(__name__)

ADVISORY_LOCK_ID = 128


def try_acquire_lock() -> bool:
    """Try to acquire a PostgreSQL advisory lock (no-op on non-PostgreSQL)."""
    from django.db import connection

    if connection.vendor != "postgresql":
        return True
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_ID])
        result = cursor.fetchone()
        return bool(result[0]) if result else False


def release_lock() -> None:
    """Release the PostgreSQL advisory lock (no-op on non-PostgreSQL)."""
    from django.db import connection

    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_ID])


class Command(BaseCommand):
    help = "Send Epic RB notifications for today. Idempotent via advisory lock + unique notify_date."

    def handle(self, *args, **options):
        if not try_acquire_lock():
            logger.info("Another send_epic_boss_notifications process is running; exiting.")
            self.stdout.write("Another instance is running; exiting.")
            return

        try:
            send_epic_boss_notification()
            self.stdout.write("Epic boss notification check complete.")
        except Exception as exc:
            logger.exception("Unexpected error in send_epic_boss_notifications")
            self.stdout.write(self.style.ERROR(f"Error: {exc}"))
        finally:
            release_lock()
