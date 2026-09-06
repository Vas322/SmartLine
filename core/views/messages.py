"""Telegram messaging views."""
import json
import logging

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from core.decorators import staff_or_404
from core.models import OutgoingMessage, ProcessingError, TelegramMessage, TelegramSettings
from core.services import messaging_service


logger = logging.getLogger(__name__)


def _active_group_topics():
    """Темы активной группы для выбора при отправке нового сообщения."""
    active = TelegramSettings.objects.filter(is_active=True).first()
    if active is None:
        return []
    return active.topics.filter(is_active=True).order_by("name")


def _read_json_body(request):
    """Return dict from JSON body or form-encoded POST (fallback)."""
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
    return request.POST.dict()


@staff_or_404
def telegram_messages(request):
    """Telegram messages page with 3 tabs: Incoming / Outgoing / Errors.

    Each table is rendered on the page (each with its own pagination,
    20 records per page) and switched via JS without reload. The active tab is
    restored from ?tab= on initial load.

    Incoming shows TelegramMessage with status PROCESSED + REGULAR (not ERROR);
    Errors shows ERROR messages together with their ProcessingError reason.
    """
    per_page = 20

    incoming_qs = TelegramMessage.objects.filter(
        status__in=[
            TelegramMessage.Status.PROCESSED,
            TelegramMessage.Status.REGULAR,
        ]
    ).order_by("-created_at")
    errors_qs = ProcessingError.objects.select_related(
        "telegram_message"
    ).order_by("-created_at")
    outgoing_qs = OutgoingMessage.objects.select_related(
        "sent_by"
    ).order_by("-created_at")

    incoming_count = incoming_qs.count()
    errors_count = errors_qs.count()
    outgoing_count = outgoing_qs.count()

    incoming_paginator = Paginator(incoming_qs, per_page)
    errors_paginator = Paginator(errors_qs, per_page)
    outgoing_paginator = Paginator(outgoing_qs, per_page)

    incoming_page = incoming_paginator.get_page(request.GET.get("incoming_page"))
    errors_page = errors_paginator.get_page(request.GET.get("errors_page"))
    outgoing_page = outgoing_paginator.get_page(request.GET.get("outgoing_page"))

    tab = request.GET.get("tab", "incoming")
    if tab not in ("incoming", "outgoing", "errors"):
        tab = "incoming"

    context = {
        "tab": tab,
        "incoming_page": incoming_page,
        "errors_page": errors_page,
        "outgoing_page": outgoing_page,
        "incoming_count": incoming_count,
        "errors_count": errors_count,
        "outgoing_count": outgoing_count,
        "telegram_topics": _active_group_topics(),
    }
    return render(request, "core/telegram_messages.html", context)


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
