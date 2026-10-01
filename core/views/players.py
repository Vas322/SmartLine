"""Player management views."""
import logging
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import F
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.decorators import member_required, staff_or_404
from core.forms import PeriodForm, PlayerEditForm, PlayerForm
from core.models import Activity, Player
from core.services import stats, summoner_bonus_service
from core.services.stats import DECIMAL_ZERO


logger = logging.getLogger(__name__)


@member_required
def player_detail(request, pk: int):
    player = get_object_or_404(Player, pk=pk)
    form = PeriodForm(
        request.GET or None,
        initial={"period": "month", "month": timezone.localdate()},
    )
    date_from, date_to = form.get_date_range()

    if form.is_valid():
        applied_period = form.cleaned_data.get("period") or form.initial.get("period") or "month"
        applied_date_from = (
            form.cleaned_data["date_from"].isoformat()
            if form.cleaned_data.get("date_from")
            else ""
        )
        applied_date_to = (
            form.cleaned_data["date_to"].isoformat()
            if form.cleaned_data.get("date_to")
            else ""
        )
        applied_month_date = form.cleaned_data.get("month")
    else:
        applied_period = form.initial.get("period") or "month"
        applied_date_from = ""
        applied_date_to = ""
        applied_month_date = None

    current_month = timezone.localdate().strftime("%Y-%m")
    applied_month = applied_month_date.strftime("%Y-%m") if applied_month_date else ""
    if applied_period == "month" and not applied_month:
        applied_month = current_month

    totals = stats.activity_totals_for_player(player, date_from, date_to)
    def_hours = totals["def_hours"] or Decimal("0")
    farm_hours = totals["farm_hours"] or Decimal("0")
    cast_hours = totals["cast_hours"] or Decimal("0")
    total_hours = def_hours + farm_hours + cast_hours

    bonus_settings = summoner_bonus_service.get_settings()
    base_payment = totals["payment"] or Decimal("0")
    bonus_total = totals["bonus"] or Decimal("0")
    total_with_bonus = base_payment + bonus_total

    reg_by_player = stats.registration_totals_for_players(date_from, date_to)
    reg_data = reg_by_player.get(
        player.pk, {"reg_payment": Decimal("0"), "reg_clans": 0, "reg_count": 0}
    )
    reg_payment = reg_data["reg_payment"]
    reg_clans = reg_data["reg_clans"]
    reg_count = reg_data["reg_count"]
    total_with_bonus += reg_payment

    summary = {
        "total_hours": total_hours,
        "adena": total_with_bonus,  # Итого выплата (с надбавками)
        "base_payment": base_payment,  # для справки в шаблоне
        "bonus_total": bonus_total,
        "def_hours": def_hours,
        "farm_hours": farm_hours,
        "cast_hours": cast_hours,
        "reg_count": reg_count,
        "reg_clans": reg_clans,
        "reg_payment": reg_payment,
    }

    sort = request.GET.get("sort", "desc")
    order = "created_at" if sort == "asc" else "-created_at"
    activities_qs = (
        Activity.objects.filter(
            player=player, created_at__range=(date_from, date_to)
        )
        .select_related("telegram_message")
        .annotate(
            row_bonus=Coalesce("bonus_kk", DECIMAL_ZERO),
            row_total=F("payment_kk") + Coalesce("bonus_kk", DECIMAL_ZERO),
        )
        .order_by(order)
    )
    paginator = Paginator(activities_qs, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    cast_count = totals["cast_count"] or 0
    summoner_count = player.summoner_count or 0

    context = {
        "form": form,
        "player": player,
        "date_from": date_from,
        "date_to": date_to,
        "summary": summary,
        "page_obj": page_obj,
        "sort": sort,
        "cast_count": cast_count,
        "bonus_settings": bonus_settings,
        "player_summoner_count": summoner_count,
        "applied_period": applied_period,
        "applied_date_from": applied_date_from,
        "applied_date_to": applied_date_to,
        "applied_month": applied_month,
        "current_month": current_month,
    }
    return render(request, "core/player_detail.html", context)


@staff_or_404
def players(request):
    players_qs = Player.objects.order_by("nickname")
    if request.method == "POST":
        form = PlayerForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("players")
    else:
        form = PlayerForm()
    return render(request, "core/players.html", {"players": players_qs, "form": form})


@staff_or_404
def player_edit(request, pk: int):
    player = get_object_or_404(Player, pk=pk)
    if request.method == "POST":
        form = PlayerEditForm(request.POST, instance=player)
        if form.is_valid():
            form.save()
            return redirect("players")
    else:
        form = PlayerEditForm(instance=player)
    return render(request, "core/player_edit.html", {"form": form, "player": player})


@staff_or_404
@require_POST
def toggle_player(request, pk: int):
    player = get_object_or_404(Player, pk=pk)
    player.is_active = not player.is_active
    player.save(update_fields=["is_active", "updated_at"])
    return redirect("players")


@staff_or_404
@require_POST
def delete_player(request, pk: int):
    player = get_object_or_404(Player, pk=pk)
    player.delete()
    return redirect("players")
