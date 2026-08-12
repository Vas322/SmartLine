"""Adapter between raw Telegram updates and the activity service."""
import logging
from datetime import datetime
from typing import Optional

from core.services.activity_service import process_telegram_message

logger = logging.getLogger(__name__)


def _extract_message(update: dict) -> Optional[dict]:
    message = update.get("message")
    if not isinstance(message, dict):
        logger.debug("Update without a message ignored; update_id=%s", update.get("update_id"))
        return None
    return message


def handle_update(update: dict) -> None:
    """Handle a single Telegram update dict."""
    message = _extract_message(update)
    if message is None:
        return

    text = message.get("text")
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
    message_date = datetime.fromtimestamp(message["date"])

    logger.info("Received telegram update chat_id=%s message_id=%s", chat_id, message_id)
    result = process_telegram_message(
        chat_id=chat_id,
        message_id=message_id,
        user_id=user_id,
        username=username,
        text=text,
        message_date=message_date,
    )
    logger.info(
        "Processed message chat_id=%s message_id=%s status=%s",
        chat_id,
        message_id,
        result.status.value,
    )