"""Statistics aggregation selectors for dashboard and player_detail."""
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

from core.models import Activity, Registration


def _activity_annotations() -> dict:
    """Shared Activity aggregation fields used by dashboard and player_detail."""
    return {
        "def_hours": Sum("amount", filter=Q(activity_type=Activity.ActivityType.DEF)),
        "farm_hours": Sum("amount", filter=Q(activity_type=Activity.ActivityType.FARM)),
        "cast_hours": Sum("amount", filter=Q(activity_type=Activity.ActivityType.CAST)),
        "cast_count": Count("pk", filter=Q(has_cast=True)),
        "payment": Coalesce(Sum("payment_kk"), Decimal("0")),
    }


def activity_totals_for_players(date_from, date_to):
    qs = (
        Activity.objects.filter(created_at__range=(date_from, date_to))
        .values("player_id")
        .annotate(**_activity_annotations())
    )
    return {row["player_id"]: row for row in qs}


def activity_totals_for_player(player, date_from, date_to):
    return Activity.objects.filter(
        player=player, created_at__range=(date_from, date_to)
    ).aggregate(**_activity_annotations())


def registration_totals_for_players(date_from, date_to):
    qs = (
        Registration.objects.filter(registered_at__range=(date_from, date_to))
        .values("player_id")
        .annotate(
            reg_payment=Coalesce(Sum("payment_kk"), Decimal("0")),
            reg_clans=Coalesce(Sum("clans_count"), 0),
        )
    )
    return {row["player_id"]: row for row in qs}
