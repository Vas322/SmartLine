"""Settings views."""
import logging
from urllib.parse import urlencode

from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import localize

from core.decorators import staff_or_404
from core.forms import (
    CastRateForm,
    EpicBossNotificationSettingsForm,
    RateForm,
    RegistrationRateForm,
    SummonerBonusForm,
    WelcomeSettingsForm,
)
from core.models import CastRate, Rate, RegistrationRate
from core.services import boss_notification_service, summoner_bonus_service, welcome_service


logger = logging.getLogger(__name__)


def _delete_rate(request, post_key: str, model) -> bool:
    """Handle a delete POST for a rate model. Returns True if redirect needed."""
    pk = request.POST.get(post_key)
    if not pk:
        return False
    try:
        model.objects.filter(pk=pk).delete()
    except (TypeError, ValueError):
        pass
    return True


def _process_rate_form(request, prefix: str, form_class, model):
    """Handle add/edit POST for one rate kind.

    Returns (handled, open_flag, form):
    - handled: True when this kind's add/edit was submitted in POST.
    - open_flag: useful only when handled; True means the add/edit form is open.
    - form: None when a redirect already happened (successful save); otherwise
      the bound form (possibly invalid) or an empty form when the edit target
      was not found.
    """
    add_key = f"add_{prefix}rate"
    edit_key = f"edit_{prefix}rate"

    if not (request.POST.get(add_key) or request.POST.get(edit_key)):
        return False, False, None

    if request.POST.get(edit_key):
        instance = model.objects.filter(pk=request.POST[edit_key]).first()
        if instance:
            form = form_class(request.POST, instance=instance)
            if form.is_valid():
                form.save()
                return True, True, None
        else:
            form = form_class()
    else:
        form = form_class(request.POST)
        if form.is_valid():
            form.save()
            return True, True, None

    return True, True, form


def _rates_redirect_for_get(request):
    """Build a redirect to the rates page preserving rate-related GET params."""
    edit_map = {
        "edit": "def",
        "edit_cast": "cast",
        "edit_reg": "reg",
        "edit_summoner_bonus": "summoner",
    }
    tab = request.GET.get("tab")
    for param, default_tab in edit_map.items():
        if request.GET.get(param):
            tab = default_tab
            break
    if tab is None:
        tab = "def"
    params = {"tab": tab}
    for param in ("edit", "edit_cast", "edit_reg", "edit_summoner_bonus"):
        if request.GET.get(param):
            params[param] = request.GET[param]
    query = urlencode(params)
    return redirect(f"{reverse('rates')}?{query}")


@staff_or_404
def settings_view(request):
    # Redirect to rates page for rate-related GET parameters.
    edit_params = ("edit", "edit_cast", "edit_reg", "edit_summoner_bonus", "tab")
    if request.method == "GET" and any(request.GET.get(p) for p in edit_params):
        return _rates_redirect_for_get(request)

    welcome_settings = welcome_service.get_welcome_settings()
    welcome_form = WelcomeSettingsForm(instance=welcome_settings)

    epic_settings = boss_notification_service.get_settings()
    epic_form = EpicBossNotificationSettingsForm(instance=epic_settings)
    epic_edit_open = bool(request.GET.get("edit_epic_boss"))

    summoner_settings = summoner_bonus_service.get_settings()
    summoner_form = SummonerBonusForm(instance=summoner_settings)
    summoner_edit_open = bool(request.GET.get("edit_summoner_bonus"))

    if request.method == "POST":
        # Summoner bonus section.
        if request.POST.get("save_summoner_bonus"):
            summoner_form = SummonerBonusForm(
                request.POST, instance=summoner_settings
            )
            if summoner_form.is_valid():
                summoner_form.save()
                return redirect("settings")
            # Форма невалидна — остаёмся на странице с ошибками и держим форму открытой.
            summoner_edit_open = True

        # Epic boss notification section.
        if request.POST.get("save_epic_boss"):
            epic_form = EpicBossNotificationSettingsForm(
                request.POST, instance=epic_settings
            )
            if epic_form.is_valid():
                epic_form.save()
                return redirect("settings")
            # Форма невалидна — оставляем её открытой для исправления.
            epic_edit_open = True

        # Welcome section actions.
        if request.POST.get("save_welcome"):
            welcome_form = WelcomeSettingsForm(
                request.POST, instance=welcome_settings
            )
            if welcome_form.is_valid():
                welcome_form.save()
                return redirect("settings")
        elif request.POST.get("reset_welcome_block"):
            welcome_service.reset_block_until()
            return redirect("settings")

    rates = Rate.objects.all()
    cast_rates = CastRate.objects.all()
    reg_rates = RegistrationRate.objects.all()
    now = timezone.now()
    welcome_blocked = (
        welcome_settings.block_until is not None
        and welcome_settings.block_until > now
    )

    active_def = rates.filter(active=True).count()
    active_cast = cast_rates.filter(active=True).count()
    active_reg = reg_rates.filter(active=True).count()

    if summoner_settings.is_enabled:
        summoner_status = f"Включено · {localize(summoner_settings.percent)}% за суммонера"
    else:
        summoner_status = "Выключено"

    welcome_on = bool(welcome_settings.welcome_text)
    welcome_status = "Включено" if welcome_on else "Выключено"

    if epic_settings.is_enabled:
        epic_status = (
            "Включено · "
            f"{epic_settings.notification_time.strftime('%H:%M')} МСК"
        )
    else:
        epic_status = "Выключено"

    tiles = [
        {
            "title": "Тарифы за DEF",
            "description": "Ставки оплаты дефенса по времени суток.",
            "status": f"{active_def} активных тарифов",
            "anchor": "rates-def",
            "on": active_def > 0,
            "href": "rates",
        },
        {
            "title": "Тарифы за каст",
            "description": "Ставки оплаты каста и перекаста форта.",
            "status": f"{active_cast} активных тарифов",
            "anchor": "rates-cast",
            "on": active_cast > 0,
            "href": "settings",
        },
        {
            "title": "Тарифы за регистрацию",
            "description": "Оплата за регистрацию кланов на атаку форта.",
            "status": f"{active_reg} активных тарифов",
            "anchor": "rates-reg",
            "on": active_reg > 0,
            "href": "settings",
        },
        {
            "title": "Надбавка за суммонеров",
            "description": "Доплата за использование суммонеров.",
            "status": summoner_status,
            "anchor": "summoner",
            "on": summoner_settings.is_enabled,
            "href": "settings",
        },
        {
            "title": "Приветствие",
            "description": "Автоприветствие новых участников Telegram-группы.",
            "status": welcome_status,
            "anchor": "welcome",
            "on": welcome_on,
            "href": "settings",
        },
        {
            "title": "Уведомления Эпик РБ",
            "description": "Уведомления о начале окон эпик-боссов.",
            "status": epic_status,
            "anchor": "epic-boss",
            "on": epic_settings.is_enabled,
            "href": "settings",
        },
    ]

    return render(
        request,
        "core/settings.html",
        {
            "welcome_form": welcome_form,
            "welcome_settings": welcome_settings,
            "welcome_blocked": welcome_blocked,
            "welcome_edit_open": bool(request.GET.get("edit_welcome")),
            "epic_form": epic_form,
            "epic_settings": epic_settings,
            "epic_preview": boss_notification_service.get_notification_preview(),
            "epic_edit_open": epic_edit_open,
            "summoner_form": summoner_form,
            "summoner_settings": summoner_settings,
            "summoner_edit_open": summoner_edit_open,
            "tiles": tiles,
        },
    )


@staff_or_404
def rates_view(request):
    edit_rate_pk = request.GET.get("edit") or request.POST.get("edit_rate")
    edit_cast_rate_pk = request.GET.get("edit_cast") or request.POST.get("edit_cast_rate")
    edit_reg_rate_pk = request.GET.get("edit_reg") or request.POST.get("edit_reg_rate")

    def_add_open = False
    cast_add_open = False
    reg_add_open = False

    rate_form = None
    cast_rate_form = None
    reg_rate_form = None

    summoner_settings = summoner_bonus_service.get_settings()
    summoner_form = SummonerBonusForm(instance=summoner_settings)
    summoner_edit_open = bool(request.GET.get("edit_summoner_bonus"))

    if request.method == "POST":
        # Summoner bonus section (independent of rate forms).
        if request.POST.get("save_summoner_bonus"):
            summoner_form = SummonerBonusForm(
                request.POST, instance=summoner_settings
            )
            if summoner_form.is_valid():
                summoner_form.save()
                return redirect("rates")
            # Форма невалидна — остаёмся на странице с ошибками и держим форму открытой.
            summoner_edit_open = True

        if _delete_rate(request, "delete_rate", Rate):
            return redirect("rates")
        if _delete_rate(request, "delete_cast_rate", CastRate):
            return redirect("rates")
        if _delete_rate(request, "delete_reg_rate", RegistrationRate):
            return redirect("rates")

        handled, def_add_open, rate_form = _process_rate_form(request, "", RateForm, Rate)
        if not handled:
            handled, cast_add_open, cast_rate_form = _process_rate_form(
                request, "cast_", CastRateForm, CastRate
            )
        if not handled:
            handled, reg_add_open, reg_rate_form = _process_rate_form(
                request, "reg_", RegistrationRateForm, RegistrationRate
            )

        if rate_form is None and def_add_open:
            return redirect("rates")
        if cast_rate_form is None and cast_add_open:
            return redirect("rates")
        if reg_rate_form is None and reg_add_open:
            return redirect("rates")

    if rate_form is None:
        rate = Rate.objects.filter(pk=edit_rate_pk).first() if edit_rate_pk else None
        rate_form = RateForm(instance=rate) if rate else RateForm()
    if cast_rate_form is None:
        cast_rate = (
            CastRate.objects.filter(pk=edit_cast_rate_pk).first()
            if edit_cast_rate_pk
            else None
        )
        cast_rate_form = CastRateForm(instance=cast_rate) if cast_rate else CastRateForm()
    if reg_rate_form is None:
        reg_rate = (
            RegistrationRate.objects.filter(pk=edit_reg_rate_pk).first()
            if edit_reg_rate_pk
            else None
        )
        reg_rate_form = RegistrationRateForm(instance=reg_rate) if reg_rate else RegistrationRateForm()

    rates = Rate.objects.all()
    cast_rates = CastRate.objects.all()
    reg_rates = RegistrationRate.objects.all()

    return render(
        request,
        "core/rates.html",
        {
            "rate_form": rate_form,
            "rates": rates,
            "edit_rate_pk": edit_rate_pk,
            "def_add_open": def_add_open,
            "cast_rate_form": cast_rate_form,
            "cast_rates": cast_rates,
            "edit_cast_rate_pk": edit_cast_rate_pk,
            "cast_add_open": cast_add_open,
            "reg_rate_form": reg_rate_form,
            "reg_rates": reg_rates,
            "edit_reg_rate_pk": edit_reg_rate_pk,
            "reg_add_open": reg_add_open,
            "summoner_form": summoner_form,
            "summoner_settings": summoner_settings,
            "summoner_edit_open": summoner_edit_open,
            "tab": request.GET.get("tab") or None,
        },
    )
