"""Thin views for the Smartline web interface."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_POST

from core.forms import (
    ActivityFilterForm,
    InstructionForm,
    PeriodForm,
    PlayerForm,
    RateForm,
)
from core.models import (
    Activity,
    Instruction,
    Player,
    ProcessingError,
    Rate,
    TelegramMessage,
)


def _percent(total_hours: Decimal, days_in_period: int) -> Decimal:
    """Attendance percent with a hard cap of 100, rounded to 2 places."""
    denominator = Decimal(days_in_period * 5)
    if denominator <= 0:
        return Decimal("0")
    percent = (total_hours / denominator) * Decimal("100")
    if percent > Decimal("100"):
        percent = Decimal("100")
    return percent.quantize(Decimal("0.01"))


def _unique_instruction_slug(base: str) -> str:
    """Return a slug that does not collide with existing Instruction slugs."""
    slug = slugify(base) or "instruction"
    original = slug
    n = 2
    while Instruction.objects.filter(slug=slug).exists():
        slug = f"{original}-{n}"
        n += 1
    return slug


@login_required
def dashboard(request):
    form = PeriodForm(request.GET or None, initial={"period": "month"})
    date_from, date_to = form.get_date_range()
    days_in_period = form.get_days_in_period()

    aggregates = (
        Activity.objects.filter(created_at__range=(date_from, date_to))
        .values("player_id")
        .annotate(
            def_hours=Sum(
                "amount",
                filter=Q(activity_type=Activity.ActivityType.DEF),
            ),
            farm_hours=Sum(
                "amount",
                filter=Q(activity_type=Activity.ActivityType.FARM),
            ),
            cast_hours=Sum(
                "amount",
                filter=Q(activity_type=Activity.ActivityType.CAST),
            ),
            payment=Coalesce(
                Sum("payment_kk"),
                Decimal("0"),
            ),
        )
    )

    totals_by_player: dict[int, dict] = {}
    for row in aggregates:
        totals_by_player[row["player_id"]] = {
            "def_hours": row["def_hours"] or Decimal("0"),
            "farm_hours": row["farm_hours"] or Decimal("0"),
            "cast_hours": row["cast_hours"] or Decimal("0"),
            "payment": row["payment"] or Decimal("0"),
        }

    rows = []
    active_players = Player.objects.filter(is_active=True)
    for player in active_players:
        totals = totals_by_player.get(player.pk, {})
        def_hours = totals.get("def_hours", Decimal("0"))
        farm_hours = totals.get("farm_hours", Decimal("0"))
        cast_hours = totals.get("cast_hours", Decimal("0"))
        total_hours = def_hours + farm_hours + cast_hours
        rows.append(
            {
                "pk": player.pk,
                "nickname": player.nickname,
                "total_hours": total_hours,
                "def_hours": def_hours,
                "farm_hours": farm_hours,
                "adena": totals.get("payment") or Decimal("0"),
                "percent": _percent(total_hours, days_in_period),
            }
        )

    rows.sort(key=lambda row: row["percent"], reverse=True)

    context = {
        "form": form,
        "date_from": date_from,
        "date_to": date_to,
        "days_in_period": days_in_period,
        "rows": rows,
    }
    return render(request, "core/dashboard.html", context)


@login_required
def player_detail(request, pk: int):
    player = get_object_or_404(Player, pk=pk)
    form = PeriodForm(request.GET or None, initial={"period": "month"})
    date_from, date_to = form.get_date_range()
    days_in_period = form.get_days_in_period()

    totals = Activity.objects.filter(
        player=player, created_at__range=(date_from, date_to)
    ).aggregate(
        def_hours=Sum(
            "amount",
            filter=Q(activity_type=Activity.ActivityType.DEF),
        ),
        farm_hours=Sum(
            "amount",
            filter=Q(activity_type=Activity.ActivityType.FARM),
        ),
        cast_hours=Sum(
            "amount",
            filter=Q(activity_type=Activity.ActivityType.CAST),
        ),
        payment=Coalesce(
            Sum("payment_kk"),
            Decimal("0"),
        ),
    )
    def_hours = totals["def_hours"] or Decimal("0")
    farm_hours = totals["farm_hours"] or Decimal("0")
    cast_hours = totals["cast_hours"] or Decimal("0")
    total_hours = def_hours + farm_hours + cast_hours

    summary = {
        "total_hours": total_hours,
        "adena": totals["payment"] or Decimal("0",),
        "def_hours": def_hours,
        "farm_hours": farm_hours,
        "percent": _percent(total_hours, days_in_period),
    }

    daily_rows = (
        Activity.objects.filter(
            player=player, created_at__range=(date_from, date_to)
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(hours=Sum("amount"))
    )
    hours_by_day = {
        row["day"]: row["hours"] or Decimal("0") for row in daily_rows
    }

    daily = []
    current = date_from.date()
    last = date_to.date()
    while current <= last:
        daily.append((current, hours_by_day.get(current, Decimal("0"))))
        current += timedelta(days=1)

    context = {
        "form": form,
        "player": player,
        "date_from": date_from,
        "date_to": date_to,
        "days_in_period": days_in_period,
        "summary": summary,
        "daily": daily,
    }
    return render(request, "core/player_detail.html", context)


@login_required
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


@login_required
@require_POST
def toggle_player(request, pk: int):
    player = get_object_or_404(Player, pk=pk)
    player.is_active = not player.is_active
    player.save(update_fields=["is_active", "updated_at"])
    return redirect("players")


@login_required
@require_POST
def delete_player(request, pk: int):
    player = get_object_or_404(Player, pk=pk)
    player.delete()
    return redirect("players")


@login_required
def activities(request):
    form = ActivityFilterForm(request.GET or None)
    activities_qs = (
        Activity.objects.select_related("player", "telegram_message")
        .order_by("-created_at")
    )
    activities_qs = form.apply_filters(activities_qs)
    return render(
        request,
        "core/activities.html",
        {"activities": activities_qs, "form": form},
    )


@login_required
def telegram_messages(request):
    messages = TelegramMessage.objects.order_by("-created_at")
    return render(
        request,
        "core/telegram_messages.html",
        {"telegram_messages": messages},
    )


@login_required
def processing_errors(request):
    errors = (
        ProcessingError.objects.select_related("telegram_message")
        .order_by("-created_at")
    )
    return render(request, "core/processing_errors.html", {"errors": errors})


@login_required
def settings_view(request):
    edit_rate_pk = request.GET.get("edit") or request.POST.get("edit_rate")

    if request.method == "POST":
        rate_pk = request.POST.get("delete_rate")
        if rate_pk:
            try:
                Rate.objects.filter(pk=rate_pk).delete()
            except (TypeError, ValueError):
                pass
            return redirect("settings")

        if request.POST.get("edit_rate"):
            rate = Rate.objects.filter(pk=request.POST["edit_rate"]).first()
            if rate:
                rate_form = RateForm(request.POST, instance=rate)
                if rate_form.is_valid():
                    rate_form.save()
                    return redirect("settings")
            else:
                rate_form = RateForm()
        else:
            rate_form = RateForm(request.POST)
            if rate_form.is_valid():
                rate_form.save()
                return redirect("settings")
    else:
        rate = Rate.objects.filter(pk=edit_rate_pk).first() if edit_rate_pk else None
        rate_form = RateForm(instance=rate) if rate else RateForm()

    rates = Rate.objects.all()
    return render(
        request,
        "core/settings.html",
        {
            "rate_form": rate_form,
            "rates": rates,
            "edit_rate_pk": edit_rate_pk,
        },
    )


@login_required
def instructions(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "add":
            slug = _unique_instruction_slug("instruction")
            instr = None
            for _ in range(5):
                try:
                    instr = Instruction.objects.create(title="Новая инструкция", slug=slug)
                    break
                except IntegrityError:
                    slug = _unique_instruction_slug("instruction")
            if instr is None:
                return redirect("instructions")
            return redirect("instruction_edit", pk=instr.pk)
        if action == "delete":
            pk = request.POST.get("pk")
            Instruction.objects.filter(pk=pk).delete()
            return redirect("instructions")
    instructions_qs = Instruction.objects.order_by("title")
    return render(
        request,
        "core/instructions.html",
        {"instructions": instructions_qs, "saved": request.GET.get("saved")},
    )


@login_required
def instruction_detail(request, pk: int):
    instr = get_object_or_404(Instruction, pk=pk)
    return render(
        request,
        "core/instruction_detail.html",
        {"instruction": instr},
    )


@login_required
def instruction_edit(request, pk: int):
    instr = get_object_or_404(Instruction, pk=pk)
    if request.method == "POST":
        form = InstructionForm(request.POST, instance=instr)
        if form.is_valid():
            saved = form.save(commit=False)
            saved.updated_by = request.user
            saved.save()
            return redirect(reverse("instructions") + "?saved=1")
    else:
        form = InstructionForm(instance=instr)
    return render(
        request,
        "core/instruction_edit.html",
        {"form": form, "instruction": instr},
    )
