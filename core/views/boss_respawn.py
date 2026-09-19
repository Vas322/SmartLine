"""Public boss respawn page view (no authentication required)."""
import logging
from datetime import timedelta

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone
from zoneinfo import ZoneInfo

from core.models import BossRespawn
from core.services import boss_respawn_service

logger = logging.getLogger(__name__)

MSK_TZ = ZoneInfo("Europe/Moscow")

ALLOWED_FILTERS = ("all", "epic", "subclass")
STALE_AFTER_HOURS = 2


def _boss_card(boss: BossRespawn) -> dict:
    """Prepare a boss card dict with render-time status and MSK window."""
    now = timezone.now()
    started = boss.respawn_start <= now <= boss.respawn_end
    start_msk = boss.respawn_start.astimezone(MSK_TZ)
    end_msk = boss.respawn_end.astimezone(MSK_TZ)
    # Countdown target: to the start if not started yet, otherwise to the end.
    countdown_msk = end_msk if started else start_msk
    return {
        "boss_name": boss.boss_name,
        "boss_type": boss.boss_type,
        "location": boss.location,
        "started": started,
        "start_msk": start_msk,
        "end_msk": end_msk,
        "countdown_msk": countdown_msk,
    }


def boss_respawn_view(request: HttpRequest) -> HttpResponse:
    raw_filter = request.GET.get("filter", "all")
    if raw_filter not in ALLOWED_FILTERS:
        raw_filter = "all"

    bosses = boss_respawn_service.get_all_bosses()
    if raw_filter == "epic":
        bosses = [b for b in bosses if b.boss_type == BossRespawn.BossType.EPIC]
    elif raw_filter == "subclass":
        bosses = [b for b in bosses if b.boss_type == BossRespawn.BossType.SUBCLASS]

    cards = [_boss_card(b) for b in bosses]

    status = boss_respawn_service.get_sync_status_for_view()
    stale = bool(
        status
        and status.last_success_at
        and timezone.now() - status.last_success_at > timedelta(hours=STALE_AFTER_HOURS)
    )

    context = {
        "cards": cards,
        "filter": raw_filter,
        "has_data": bool(cards),
        "stale": stale,
    }
    return render(request, "core/boss_respawn.html", context)
