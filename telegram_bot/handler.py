"""Adapter between raw Telegram updates and the activity service."""
import logging
from datetime import datetime
from django.utils import timezone
from django.conf import settings

from core.services.activity_service import (
    process_telegram_edit,
    process_telegram_message,
    ProcessResultStatus,
)
from core.services.notification_service import notify_activity_reaction
from core.services import schedule_mirror_service

logger = logging.getLogger(__name__)
MSK = timezone.get_fixed_timezone(180)  # UTC+3, фиксированный пояс Москвы


def _is_denylisted(text: str) -> bool:
    """Return True if text should be skipped for schedule mirroring."""
    if not text:
        return True
    stripped = text.lstrip()
    if stripped.startswith("/"):
        return True
    lowered = stripped.lower()
    for prefix in settings.SCHEDULE_MIRROR_IGNORE_PREFIXES:
        if lowered.startswith(prefix.lower()):
            return True
    return False


def handle_update(update: dict) -> None:
    """Handle a single Telegram update dict."""
    # [BRIDGE-DBG] Debug log for all incoming updates (before any routing)
    msg = (
        update.get("message")
        or update.get("edited_message")
        or update.get("channel_post")
        or update.get("edited_channel_post")
    )
    if isinstance(msg, dict):
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        msg_id = msg.get("message_id")
        from_user = msg.get("from") or {}
        from_id = from_user.get("id")
        from_username = from_user.get("username", "") or ""
        forward_from = msg.get("forward_from") or {}
        fwd_username = forward_from.get("username", "") or ""
        text = msg.get("text") or msg.get("caption") or ""
        logger.info(
            "[BRIDGE-DBG] chat_id=%s msg_id=%s from_id=%s from_username=%s fwd_username=%s text=%r",
            chat_id,
            msg_id,
            from_id,
            from_username,
            fwd_username,
            text[:80],
        )

    # Handle channel_post / edited_channel_post (schedule source channel)
    channel_post = update.get("channel_post")
    edited_channel_post = update.get("edited_channel_post")
    if isinstance(channel_post, dict) or isinstance(edited_channel_post, dict):
        is_edit = isinstance(edited_channel_post, dict)
        message = edited_channel_post if is_edit else channel_post
        chat_id = message["chat"]["id"]
        message_id = message["message_id"]
        text = message.get("text") or message.get("caption") or ""

        if chat_id == settings.SCHEDULE_SOURCE_CHAT_ID:
            if _is_denylisted(text):
                logger.info(
                    "Skipping schedule mirror for denylisted/empty channel post: chat_id=%s msg_id=%s",
                    chat_id,
                    message_id,
                )
                return
            try:
                schedule_mirror_service.handle_source_message(
                    source_chat_id=chat_id,
                    source_message_id=message_id,
                    text=text,
                    alliance_bot_username=settings.ALLIANCE_BOT_USERNAME,
                    is_edit=is_edit,
                )
            except Exception:  # never break main flow
                logger.exception("Failed to mirror schedule message from channel")
                try:
                    from core.services.notification_service import notify_kl
                    notify_kl("Smartline: не удалось зеркалировать расписание из канала (см. логи бота).")
                except Exception:
                    pass
            return

    message = update.get("message")
    is_edit = False
    if not isinstance(message, dict):
        message = update.get("edited_message")
        is_edit = True
    if not isinstance(message, dict):
        logger.debug(
            "Update without a message ignored; update_id=%s",
            update.get("update_id"),
        )
        return None

    text = message.get("text") or message.get("caption")
    if text is None:
        logger.info(
            "Message without text ignored; message_id=%s",
            message.get("message_id"),
        )
        return

    chat_id = message["chat"]["id"]
    message_id = message["message_id"]
    user_info = message.get("from") or {}
    user_id = user_info.get("id")
    username = user_info.get("username", "") or ""
    date = message.get("edit_date") if is_edit else message.get("date")
    message_date = datetime.fromtimestamp(date, tz=MSK)
    message_thread_id = message.get("message_thread_id")

    logger.info(
        "Received telegram update chat_id=%s message_id=%s is_edit=%s",
        chat_id,
        message_id,
        is_edit,
    )
    try:
        if is_edit:
            result = process_telegram_edit(
                chat_id=chat_id,
                message_id=message_id,
                text=text,
                message_date=message_date,
                user_id=user_id,
                username=username,
                message_thread_id=message_thread_id,
            )
        else:
            result = process_telegram_message(
                chat_id=chat_id,
                message_id=message_id,
                user_id=user_id,
                username=username,
                text=text,
                message_date=message_date,
                message_thread_id=message_thread_id,
            )
        if result.status == ProcessResultStatus.ACTIVITY_CREATED:
            notify_activity_reaction(result.telegram_message, "🎉")
        logger.info(
            "Processed message chat_id=%s message_id=%s status=%s",
            chat_id,
            message_id,
            result.status.value,
        )
    except Exception:
        logger.exception("Failed to process telegram message")
        try:
            from core.services.notification_service import notify_kl
            notify_kl("Smartline: ошибка обработки сообщения (см. логи бота).")
        except Exception:
            pass
