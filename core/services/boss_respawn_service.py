"""Business logic for syncing and querying boss respawn data (craft-calc.ru)."""
import logging
import urllib.request
from typing import Optional

from django.conf import settings
from django.utils import timezone

from core.models import BossRespawn, BossRespawnSyncStatus
from core.services.boss_respawn_parser import BossData, parse_bosses_from_html

logger = logging.getLogger(__name__)

FETCH_TIMEOUT_SECONDS = 30


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
