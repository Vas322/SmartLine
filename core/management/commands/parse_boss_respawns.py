"""Management command to sync boss respawn data from craft-calc.ru."""
import logging
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.services.boss_respawn_service import fetch_and_sync, get_sync_status

logger = logging.getLogger(__name__)

ADVISORY_LOCK_ID = 127
DEFAULT_INTERVAL_MINUTES = 30


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
    help = "Sync boss respawn data. Rate-limited (30 min) and guarded by an advisory lock."

    def handle(self, *args, **options):
        from django.conf import settings

        interval = getattr(settings, "BOSS_RESPAWN_PARSE_INTERVAL_MINUTES", DEFAULT_INTERVAL_MINUTES)

        if not try_acquire_lock():
            logger.info("Another parse_boss_respawns process is running; exiting.")
            self.stdout.write("Another instance is running; exiting.")
            return

        try:
            status = get_sync_status()
            if (
                status.last_success_at
                and timezone.now() - status.last_success_at < timedelta(minutes=interval)
            ):
                logger.info("Boss respawn synced recently; skipping.")
                self.stdout.write("Synced recently; skipping.")
                return

            ok = fetch_and_sync()
            if ok:
                logger.info("Boss respawn sync OK.")
                self.stdout.write(self.style.SUCCESS("Boss respawn sync OK."))
            else:
                logger.error("Boss respawn sync failed.")
                self.stdout.write(self.style.ERROR("Boss respawn sync failed."))
        finally:
            release_lock()
