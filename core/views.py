"""Thin views for the Smartline web interface."""
from datetime import timedelta
from decimal import Decimal
import json
import logging
from base64 import urlsafe_b64decode, urlsafe_b64encode

from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib import messages
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.text import slugify
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import force_bytes, force_str
from django.views.decorators.http import require_POST

from core.decorators import member_required, staff_or_404
from core.forms import (
    ActivityFilterForm,
    CastRateForm,
    InstructionForm,
    PeriodForm,
    PlayerEditForm,
    PlayerForm,
    RateForm,
    RegistrationRateForm,
    SignUpForm,
)
from core.models import (
    Activity,
    CastRate,
    Instruction,
    OutgoingMessage,
    Player,
    ProcessingError,
    Rate,
    Registration,
    RegistrationRate,
    ScheduleMirror,
    TelegramMessage,
    TelegramSettings,
    TelegramTopic,
)
from core.services import messaging_service, schedule_mirror_service


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


@member_required
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
            cast_count=Count("pk", filter=Q(has_cast=True)),
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
            "cast_count": row["cast_count"] or 0,
            "payment": row["payment"] or Decimal("0"),
        }

    # Registrations aggregation (registered_at__range for the period)
    reg_aggregates = (
        Registration.objects.filter(registered_at__range=(date_from, date_to))
        .values("player_id")
        .annotate(
            reg_payment=Coalesce(Sum("payment_kk"), Decimal("0")),
            reg_clans=Coalesce(Sum("clans_count"), 0),
        )
    )
    reg_by_player = {
        row["player_id"]: {"payment": row["reg_payment"], "clans": row["reg_clans"]}
        for row in reg_aggregates
    }

    rows = []
    active_players = Player.objects.filter(is_active=True)
    for player in active_players:
        totals = totals_by_player.get(player.pk, {})
        def_hours = totals.get("def_hours", Decimal("0"))
        farm_hours = totals.get("farm_hours", Decimal("0"))
        cast_hours = totals.get("cast_hours", Decimal("0"))
        total_hours = def_hours + farm_hours + cast_hours
        reg_data = reg_by_player.get(player.pk, {"payment": Decimal("0"), "clans": 0})
        reg_payment = reg_data["payment"]
        reg_clans = reg_data["clans"]
        rows.append(
            {
                "pk": player.pk,
                "nickname": player.nickname,
                "total_hours": total_hours,
                "def_hours": def_hours,
                "farm_hours": farm_hours,
                "cast_count": totals.get("cast_count", 0),
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
        (row["payment"] for row in reg_by_player.values()), Decimal("0")
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


@staff_or_404
def player_detail(request, pk: int):
    player = get_object_or_404(Player, pk=pk)
    form = PeriodForm(request.GET or None, initial={"period": "month"})
    date_from, date_to = form.get_date_range()
    days_in_period = form.get_days_in_period()

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
    else:
        applied_period = form.initial.get("period") or "month"
        applied_date_from = ""
        applied_date_to = ""

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
        "adena": totals["payment"] or Decimal("0"),
        "def_hours": def_hours,
        "farm_hours": farm_hours,
        "percent": _percent(total_hours, days_in_period),
    }

    sort = request.GET.get("sort", "desc")
    order = "created_at" if sort == "asc" else "-created_at"
    activities_qs = (
        Activity.objects.filter(
            player=player, created_at__range=(date_from, date_to)
        )
        .select_related("telegram_message")
        .order_by(order)
    )
    paginator = Paginator(activities_qs, 50)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    cast_count = Activity.objects.filter(
        player=player, created_at__range=(date_from, date_to), has_cast=True
    ).count()

    context = {
        "form": form,
        "player": player,
        "date_from": date_from,
        "date_to": date_to,
        "summary": summary,
        "page_obj": page_obj,
        "sort": sort,
        "cast_count": cast_count,
        "applied_period": applied_period,
        "applied_date_from": applied_date_from,
        "applied_date_to": applied_date_to,
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


@staff_or_404
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


def _active_group_topics():
    """Темы активной группы для выбора при отправке нового сообщения."""
    active = TelegramSettings.objects.filter(is_active=True).first()
    if active is None:
        return []
    return active.topics.filter(is_active=True).order_by("name")


@staff_or_404
def telegram_messages(request):
    """Telegram messages page with Incoming / Outgoing / All tabs.

    All three tables are rendered on the page (each with its own pagination,
    20 records per page) and switched via JS without reload. The active tab is
    restored from ?tab= on initial load.
    """
    per_page = 20

    incoming_count = TelegramMessage.objects.count()
    outgoing_count = OutgoingMessage.objects.count()

    incoming_qs = TelegramMessage.objects.order_by("-created_at")
    outgoing_qs = OutgoingMessage.objects.select_related("sent_by").order_by("-created_at")

    incoming_paginator = Paginator(incoming_qs, per_page)
    outgoing_paginator = Paginator(outgoing_qs, per_page)

    incoming_page = incoming_paginator.get_page(request.GET.get("incoming_page"))
    outgoing_page = outgoing_paginator.get_page(request.GET.get("outgoing_page"))

    # Merged chronological list for the "All" tab.
    combined = []
    for tm in TelegramMessage.objects.all().values(
        "id", "created_at", "message_date", "text", "telegram_chat_id",
        "telegram_message_id", "telegram_username", "status",
    ):
        combined.append(
            {
                "kind": "incoming",
                "sort_key": tm["created_at"],
                "tm": tm,
            }
        )
    for om in OutgoingMessage.objects.all().values(
        "id", "created_at", "sent_at", "text", "telegram_chat_id",
        "telegram_message_id", "sent_by__username", "topic_name",
        "reply_to_message_id", "reply_to_text", "status",
    ):
        combined.append(
            {
                "kind": "outgoing",
                "sort_key": om["sent_at"] or om["created_at"],
                "om": om,
            }
        )
    combined.sort(key=lambda item: item["sort_key"], reverse=True)

    all_paginator = Paginator(combined, per_page)
    all_page = all_paginator.get_page(request.GET.get("all_page"))

    tab = request.GET.get("tab", "incoming")
    if tab not in ("incoming", "outgoing", "all"):
        tab = "incoming"

    context = {
        "tab": tab,
        "incoming_page": incoming_page,
        "outgoing_page": outgoing_page,
        "all_page": all_page,
        "incoming_count": incoming_count,
        "outgoing_count": outgoing_count,
        "total_count": incoming_count + outgoing_count,
        "telegram_topics": _active_group_topics(),
    }
    return render(request, "core/telegram_messages.html", context)


def _read_json_body(request):
    """Return dict from JSON body or form-encoded POST (fallback)."""
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
    return request.POST.dict()


@require_POST
def send_reply(request):
    """AJAX API: reply to an incoming Telegram message."""
    if not request.user.is_staff:
        return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)

    data = _read_json_body(request)
    telegram_message_id = data.get("telegram_message_id")
    text = data.get("text", "")

    if telegram_message_id is None:
        return JsonResponse({"ok": False, "error": "Не указан telegram_message_id."}, status=400)
    telegram_message = get_object_or_404(TelegramMessage, pk=telegram_message_id)

    try:
        outgoing = messaging_service.send_reply(
            user=request.user,
            telegram_message=telegram_message,
            text=text,
        )
    except messaging_service.MessagingError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except Exception:
        logger.exception("Unexpected error sending reply")
        return JsonResponse({"ok": False, "error": "Не удалось отправить сообщение."}, status=500)

    return JsonResponse({"ok": True, "message_id": outgoing.telegram_message_id})


@require_POST
def send_message(request):
    """AJAX API: send a new message to the clan group."""
    if not request.user.is_staff:
        return JsonResponse({"ok": False, "error": "Недостаточно прав."}, status=403)

    data = _read_json_body(request)
    text = data.get("text", "")
    raw_thread_id = data.get("thread_id")

    thread_id = None
    if raw_thread_id not in (None, ""):
        try:
            thread_id = int(raw_thread_id)
        except (TypeError, ValueError):
            return JsonResponse({"ok": False, "error": "Некорректный thread_id."}, status=400)

    try:
        outgoing = messaging_service.send_new_message(
            user=request.user,
            text=text,
            thread_id=thread_id,
        )
    except messaging_service.MessagingError as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=400)
    except Exception:
        logger.exception("Unexpected error sending new message")
        return JsonResponse({"ok": False, "error": "Не удалось отправить сообщение."}, status=500)

    return JsonResponse({"ok": True, "message_id": outgoing.telegram_message_id})


@staff_or_404
def processing_errors(request):
    errors = (
        ProcessingError.objects.select_related("telegram_message")
        .order_by("-created_at")
    )
    return render(request, "core/processing_errors.html", {"errors": errors})


@staff_or_404
def settings_view(request):
    edit_rate_pk = request.GET.get("edit") or request.POST.get("edit_rate")
    edit_cast_rate_pk = request.GET.get("edit_cast") or request.POST.get("edit_cast_rate")
    edit_reg_rate_pk = request.GET.get("edit_reg") or request.POST.get("edit_reg_rate")

    def_add_open = False
    cast_add_open = False
    reg_add_open = False

    rate_form = None
    cast_rate_form = None
    reg_rate_form = None

    if request.method == "POST":
        rate_pk = request.POST.get("delete_rate")
        if rate_pk:
            try:
                Rate.objects.filter(pk=rate_pk).delete()
            except (TypeError, ValueError):
                pass
            return redirect("settings")

        cast_rate_pk = request.POST.get("delete_cast_rate")
        if cast_rate_pk:
            try:
                CastRate.objects.filter(pk=cast_rate_pk).delete()
            except (TypeError, ValueError):
                pass
            return redirect("settings")

        reg_rate_pk = request.POST.get("delete_reg_rate")
        if reg_rate_pk:
            try:
                RegistrationRate.objects.filter(pk=reg_rate_pk).delete()
            except (TypeError, ValueError):
                pass
            return redirect("settings")

        if request.POST.get("add_rate") or request.POST.get("edit_rate"):
            def_add_open = True
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
        elif request.POST.get("add_cast_rate") or request.POST.get("edit_cast_rate"):
            cast_add_open = True
            if request.POST.get("edit_cast_rate"):
                cast_rate = CastRate.objects.filter(pk=request.POST["edit_cast_rate"]).first()
                if cast_rate:
                    cast_rate_form = CastRateForm(request.POST, instance=cast_rate)
                    if cast_rate_form.is_valid():
                        cast_rate_form.save()
                        return redirect("settings")
                else:
                    cast_rate_form = CastRateForm()
            else:
                cast_rate_form = CastRateForm(request.POST)
                if cast_rate_form.is_valid():
                    cast_rate_form.save()
                    return redirect("settings")
        elif request.POST.get("add_reg_rate") or request.POST.get("edit_reg_rate"):
            reg_add_open = True
            if request.POST.get("edit_reg_rate"):
                reg_rate = RegistrationRate.objects.filter(pk=request.POST["edit_reg_rate"]).first()
                if reg_rate:
                    reg_rate_form = RegistrationRateForm(request.POST, instance=reg_rate)
                    if reg_rate_form.is_valid():
                        reg_rate_form.save()
                        return redirect("settings")
                else:
                    reg_rate_form = RegistrationRateForm()
            else:
                reg_rate_form = RegistrationRateForm(request.POST)
                if reg_rate_form.is_valid():
                    reg_rate_form.save()
                    return redirect("settings")

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
        "core/settings.html",
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
        },
    )


@member_required
def instructions(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("add", "delete") and not request.user.is_staff:
            return HttpResponseForbidden("Недостаточно прав для управления инструкциями.")
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


@member_required
def instruction_detail(request, pk: int):
    instr = get_object_or_404(Instruction, pk=pk)
    return render(
        request,
        "core/instruction_detail.html",
        {"instruction": instr},
    )


@staff_or_404
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


@member_required
def schedule_mirror(request):
    """Manage schedule mirroring from alliance bot to clan group."""
    current_mirror = ScheduleMirror.objects.filter(is_active=True).first()
    current_text = schedule_mirror_service.get_current_text()

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "reconcile":
            if not request.user.is_staff:
                return HttpResponseForbidden("Только для персонала.")
            schedule_mirror_service.reconcile_all()
            messages.success(request, "Синхронизация выполнена.")
            return redirect("schedule_mirror")

    context = {
        "current_mirror": current_mirror,
        "current_text": current_text,
    }
    return render(request, "core/schedule_mirror.html", context)


logger = logging.getLogger(__name__)

MEMBERS_GROUP = "Members"


def _send_activation_email(request, user):
    """Send email with activation link."""
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    activation_path = reverse("activate", kwargs={"uidb64": uid, "token": token})
    activation_url = request.build_absolute_uri(activation_path)
    subject = "Smartline — Подтверждение регистрации"
    message = (
        f"Здравствуйте, {user.username}!\n\n"
        f"Для завершения регистрации перейдите по ссылке:\n"
        f"{activation_url}\n\n"
        f"Ссылка действительна в течение 48 часов.\n\n"
        f"Если вы не регистрировались в Smartline — игнорируйте это письмо."
    )
    send_mail(subject, message, None, [user.email])


def signup_view(request):
    """User registration with email verification."""
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                is_active=False,
            )
            _send_activation_email(request, user)
            logger.info("Registration: user %s created, activation email sent", user.username)
            return redirect("activation_sent")
    else:
        form = SignUpForm()
    return render(request, "core/signup.html", {"form": form})


def activate_view(request, uidb64, token):
    """Activate user account from email link."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        members_group, _ = Group.objects.get_or_create(name=MEMBERS_GROUP)
        user.groups.add(members_group)
        logger.info("Activation: user %s activated", user.username)
        return render(request, "core/activation_complete.html")
    
    logger.warning("Activation failed: invalid token or user")
    return render(request, "core/activation_invalid.html")


def activation_sent_view(request):
    """Show 'check your email' message."""
    return render(request, "core/activation_sent.html")


@login_required
def profile_view(request):
    """User profile page."""
    return render(request, "core/profile.html")
