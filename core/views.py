"""Thin views for the Smartline web interface."""
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.forms import ActivityFilterForm, PeriodForm, PlayerForm, SettingForm
from core.models import Activity, Player, ProcessingError, Setting, TelegramMessage

SettingFormSet = modelformset_factory(Setting, form=SettingForm, extra=0)


@login_required
def dashboard(request):
    form = PeriodForm(request.GET or None)
    date_from, date_to = form.get_date_range()

    activities_qs = Activity.objects.filter(
        created_at__range=(date_from, date_to)
    )
    stats = activities_qs.aggregate(
        total_activities=Count("id"),
        players_count=Count("player", distinct=True),
        def_hours=Sum(
            "amount",
            filter=Q(activity_type=Activity.ActivityType.DEF),
        ),
        farm_hours=Sum(
            "amount",
            filter=Q(activity_type=Activity.ActivityType.FARM),
        ),
    )

    def_hours = stats["def_hours"] or Decimal("0")
    farm_hours = stats["farm_hours"] or Decimal("0")
    stats["def_hours"] = def_hours
    stats["farm_hours"] = farm_hours
    total_hours = def_hours + farm_hours
    paid_hours = def_hours

    context = {
        "form": form,
        "date_from": date_from,
        "date_to": date_to,
        "stats": stats,
        "total_hours": total_hours,
        "paid_hours": paid_hours,
    }
    return render(request, "core/dashboard.html", context)


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
    formset = SettingFormSet(
        request.POST or None,
        queryset=Setting.objects.order_by("key"),
    )
    if request.method == "POST" and formset.is_valid():
        formset.save()
        return redirect("settings")
    return render(request, "core/settings.html", {"formset": formset})
