"""Business logic for syncing and querying boss respawn data (craft-calc.ru)."""
import logging
import urllib.request
from typing import Optional
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

from core.models import BossRespawn, BossRespawnSyncStatus
from core.services.boss_respawn_parser import BossData, parse_bosses_from_html

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 30

# Parsed respawn times are naive Moscow local time; this zone is attached so
# they are comparable with the aware datetimes read back from the database.
MSK_TZ = ZoneInfo("Europe/Moscow")


def get_sync_status() -> BossRespawnSyncStatus:
    """Return the singleton BossRespawnSyncStatus (always works with pk=1)."""
    status, _ = BossRespawnSyncStatus.objects.get_or_create(pk=1)
    return status


def _fetch_html() -> str:
    """Fetch the boss respawn page HTML from the configured source URL."""
    url = settings.BOSS_RESPAWN_SOURCE_URL
    with urllib.request.urlopen(url, timeout=FETCH_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8")


def _upsert_bosses(bosses: list[BossData]) -> None:
    """Upsert parsed bosses into BossRespawn (dedupe by unique boss_name)."""
    for boss in bosses:
        try:
            BossRespawn.objects.update_or_create(
                boss_name=boss.boss_name,
                defaults={
                    "boss_type": boss.boss_type,
                    "respawn_start": boss.respawn_start,
                    "respawn_end": boss.respawn_end,
                    "location": boss.location,
                    "raw_data": {
                        "started": boss.started,
                        "timezone_attr": boss.timezone_attr,
                    },
                    "is_parsed_successfully": True,
                    "last_error": "",
                },
            )
        except Exception as exc:
            logger.exception("Failed to upsert boss %s", boss.boss_name)
            BossRespawn.objects.filter(boss_name=boss.boss_name).update(
                is_parsed_successfully=False,
                last_error=str(exc),
            )


def _reparse_existing_bosses(bosses: list[BossData]) -> None:
    """Re-parse existing bosses from the DB to fix previously stored times.

    Historical rows were saved with an erroneous EDT→UTC conversion (+7h off).
    Compare each stored (aware MSK) row against the freshly parsed (naive MSK)
    values and rewrite them when they differ.
    """
    updated_count = 0
    for boss in BossRespawn.objects.all():
        parsed = next(
            (b for b in bosses if b.boss_name == boss.boss_name), None
        )
        if parsed is None:
            continue
        parsed_start = parsed.respawn_start.replace(tzinfo=MSK_TZ)
        parsed_end = parsed.respawn_end.replace(tzinfo=MSK_TZ)
        if (
            boss.respawn_start != parsed_start
            or boss.respawn_end != parsed_end
        ):
            boss.respawn_start = parsed_start
            boss.respawn_end = parsed_end
            boss.save(update_fields=["respawn_start", "respawn_end"])
            updated_count += 1
    logger.info("Boss respawn times updated: %s", updated_count)


def fetch_and_sync() -> bool:
    """Fetch the page, parse and upsert bosses, then update the sync status.

    Returns True on success (at least one card parsed and stored), False on
    failure. Previously stored valid data is left intact on failure so the
    public page keeps showing the last known-good schedule.
    """
    status = get_sync_status()
    status.last_attempt_at = timezone.now()
    status.save(update_fields=["last_attempt_at"])

    try:
        html = _fetch_html()
        bosses = parse_bosses_from_html(html)
        if not bosses:
            raise RuntimeError("No boss cards parsed — page markup may have changed")
        _upsert_bosses(bosses)
        _reparse_existing_bosses(bosses)
        status.last_success_at = timezone.now()
        status.last_error = ""
        status.last_error_at = None
        status.save(update_fields=["last_success_at", "last_error", "last_error_at"])
        logger.info(
            "Boss respawn synced: %s bosses (%s epic, %s subclass)",
            len(bosses),
            sum(1 for b in bosses if b.boss_type == "EPIC"),
            sum(1 for b in bosses if b.boss_type == "SUBCLASS"),
        )
        return True
    except Exception as exc:
        logger.error("Boss respawn sync failed: %s", type(exc).__name__)
        status.last_error_at = timezone.now()
        status.last_error = str(exc)
        status.save(update_fields=["last_error_at", "last_error"])
        return False


def get_all_bosses() -> list[BossRespawn]:
    """Return all bosses ordered by respawn_start."""
    return list(BossRespawn.objects.order_by("respawn_start"))


def get_sync_status_for_view() -> Optional[BossRespawnSyncStatus]:
    """Return sync status if it exists (for the public page), else None."""
    return BossRespawnSyncStatus.objects.filter(pk=1).first()
