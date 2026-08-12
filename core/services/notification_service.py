"""Notification to the clan leader via Telegram."""
import logging
from typing import List

import requests
from django.conf import settings

from core.models import ProcessingError

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
            logger.error("Failed to send Telegram notification to chat_id=%s: %s", chat_id, exc)
    return sent


def notify_processing_error(error: ProcessingError) -> None:
    """Build a notification about a processing error and send it to the KL."""
    message = error.telegram_message
    text = (
        "Smartline: ошибка обработки Telegram-сообщения\n"
        f"Причина: {error.reason}\n"
        f"Текст: {message.text}\n"
        f"Username: {message.telegram_username or '-'}\n"
        f"Дата: {message.message_date.isoformat()}\n"
        f"Message ID: {message.telegram_message_id}"
    )
    if notify_kl(text):
        error.status = ProcessingError.Status.NOTIFIED
        error.save(update_fields=["status"])
