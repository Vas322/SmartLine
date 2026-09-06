"""Dashboard views."""
import logging
from decimal import Decimal

from django.shortcuts import render

from core.decorators import member_required
from core.forms import PeriodForm
from core.models import Player
from core.services import stats
from core.views.common import _percent


logger = logging.getLogger(__name__)


@member_required
def dashboard(request):
    form = PeriodForm(request.GET or None, initial={"period": "month"})
    date_from, date_to = form.get_date_range()
    days_in_period = form.get_days_in_period()

    totals_by_player: dict[int, dict] = {
        pid: {
            "def_hours": row["def_hours"] or Decimal("0"),
            "farm_hours": row["farm_hours"] or Decimal("0"),
            "cast_hours": row["cast_hours"] or Decimal("0"),
            "cast_count": row["cast_count"] or 0,
            "payment": row["payment"] or Decimal("0"),
        }
        for pid, row in stats.activity_totals_for_players(date_from, date_to).items()
    }

    # Registrations aggregation (registered_at__range for the period)
    reg_by_player = stats.registration_totals_for_players(date_from, date_to)

    rows = []
    active_players = Player.objects.filter(is_active=True).only("id", "nickname")
    for player in active_players:
        totals = totals_by_player.get(player.pk, {})
        def_hours = totals.get("def_hours", Decimal("0"))
        farm_hours = totals.get("farm_hours", Decimal("0"))
        cast_hours = totals.get("cast_hours", Decimal("0"))
        total_hours = def_hours + farm_hours + cast_hours
        reg_data = reg_by_player.get(
            player.pk, {"reg_payment": Decimal("0"), "reg_clans": 0}
        )
        reg_payment = reg_data["reg_payment"]
        reg_clans = reg_data["reg_clans"]
        cast_count = totals.get("cast_count", 0)
        if total_hours == 0 and cast_count == 0 and reg_clans == 0:
            continue
        rows.append(
            {
                "pk": player.pk,
                "nickname": player.nickname,
                "total_hours": total_hours,
                "def_hours": def_hours,
                "farm_hours": farm_hours,
                "cast_count": cast_count,
                "adena": (totals.get("payment") or Decimal("0")) + reg_payment,
                "registration": reg_clans,
                "percent": _percent(total_hours, days_in_period),
            }
        )

    rows.sort(key=lambda row: row["percent"], reverse=True)

    # Total payout for the period (activities + registrations)
    total_activity_payment = sum(
        (row["payment"] for row in totals_by_player.values()), Decimal("0")
    )
    total_registration_payment = sum(
        (row["reg_payment"] for row in reg_by_player.values()), Decimal("0")
    )
    total_payout = total_activity_payment + total_registration_payment

    context = {
        "form": form,
        "date_from": date_from,
        "date_to": date_to,
        "days_in_period": days_in_period,
        "rows": rows,
        "total_payout": total_payout,
    }
    return render(request, "core/dashboard.html", context)
