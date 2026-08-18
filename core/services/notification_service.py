"""Notification to the clan leader via Telegram."""
import logging
from typing import List

import requests
from django.conf import settings

from core.models import ProcessingError
from core.error_messages import friendly_error_message

logger = logging.getLogger(__name__)

_TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def _admin_chat_ids() -> List[str]:
    raw = settings.ADMIN_TELEGRAM_CHAT_IDS or ""
    return [item.strip() for item in raw.split(",") if item.strip()]


def notify_kl(message_text: str) -> bool:
    """Send a message to all configured clan-leader chats.

    Returns True if at least one notification was sent successfully.
    Never raises: notification failures are logged and swallowed so the
    main message-processing flow is not broken.
    """
    chat_ids = _admin_chat_ids()
    token = settings.TELEGRAM_BOT_TOKEN
    if not chat_ids:
        logger.warning("No ADMIN_TELEGRAM_CHAT_IDS configured; notification skipped")
        return False
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured; notification skipped")
        return False

    sent = False
    for chat_id in chat_ids:
        try:
            response = requests.post(
                _TELEGRAM_API_URL.format(token=token),
                data={"chat_id": chat_id, "text": message_text},
                timeout=10,
            )
            response.raise_for_status()
            sent = True
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None)
            detail = type(exc).__name__
            if status is not None:
                logger.error(
                    "Failed to send Telegram notification to chat_id=%s: %s (status=%s)",
                    chat_id, detail, status,
                )
            else:
                logger.error(
                    "Failed to send Telegram notification to chat_id=%s: %s",
                    chat_id, detail,
                )
    return sent


def notify_processing_error(error: ProcessingError) -> None:
    """Build a notification about a processing error and reply in the group."""
    message = error.telegram_message
    text = (
        "Smartline: ошибка обработки Telegram-сообщения\n"
        f"Причина: {friendly_error_message(error.reason)}\n"
        f"Текст: {message.text}\n"
        f"Username: {message.telegram_username or '-'}\n"
        f"Дата: {message.message_date.isoformat()}\n"
        f"Message ID: {message.telegram_message_id}"
    )
    if notify_group_reply(message, text):
        error.status = ProcessingError.Status.NOTIFIED
        error.save(update_fields=["status"])


def notify_group_reply(telegram_message, text: str) -> bool:
    """Reply to the original message in the same group.

    Returns True if the reply was sent successfully. Never raises:
    notification failures are logged and swallowed so the main
    message-processing flow is not broken.
    """
    from telegram_bot.bot import TelegramBot

    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured; group reply skipped")
        return False
    try:
        TelegramBot(token=token).send_message(
            chat_id=telegram_message.telegram_chat_id,
            text=text,
            reply_to_message_id=telegram_message.telegram_message_id,
        )
    except Exception as exc:  # никогда не ломает обработку сообщения
        logger.warning(
            "Failed to send group reply to message_id=%s: %s",
            telegram_message.telegram_message_id,
            type(exc).__name__,
        )
        return False
    return True


def notify_activity_reaction(telegram_message, emoji: str = "🎉") -> bool:
    """Put a reaction emoji on the original message to signal success.

    Best-effort: never raises, so message processing is never broken.
    """
    from telegram_bot.bot import TelegramBot

    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN is not configured; reaction skipped")
        return False
    try:
        TelegramBot(token=token).set_message_reaction(
            chat_id=telegram_message.telegram_chat_id,
            message_id=telegram_message.telegram_message_id,
            emoji=emoji,
        )
        return True
    except Exception as exc:  # никогда не ломает обработку сообщения
        logger.warning(
            "Failed to set reaction on message_id=%s: %s",
            telegram_message.telegram_message_id,
            exc,
        )
        return False
