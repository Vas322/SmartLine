"""Business logic for sending messages from the web interface to Telegram."""
import logging
from typing import Optional

from core.models import OutgoingMessage, TelegramMessage, TelegramSettings, TelegramTopic

logger = logging.getLogger(__name__)

MAX_TEXT_LENGTH = 4096


class MessagingError(Exception):
    """Raised when a message cannot be sent (validation or Telegram failure)."""


def _normalize_text(text: str) -> str:
    """Validate and normalize message text.

    - Empty text is not allowed.
    - Text longer than MAX_TEXT_LENGTH is truncated (hard Telegram limit).
    """
    if text is None or text.strip() == "":
        raise MessagingError("Текст сообщения не может быть пустым.")
    return text[:MAX_TEXT_LENGTH]


def _topic_name_by_thread_id(thread_id: Optional[int]) -> str:
    """Return the active topic name by thread_id, or '' for general flow."""
    if thread_id is None:
        return ""
    topic = TelegramTopic.objects.filter(
        thread_id=thread_id,
        group__is_active=True,
        is_active=True,
    ).first()
    return topic.name if topic else ""


def _create_outgoing(
    *,
    user,
    chat_id: int,
    text: str,
    reply_to_message_id: Optional[int],
    reply_to_text: str,
    topic_name: str,
) -> OutgoingMessage:
    """Create an OutgoingMessage audit record in PENDING state.

    The record is created BEFORE calling Telegram so the attempt is always
    audited, even if the API call or the follow-up update fails.
    telegram_message_id is unknown yet, so it is set to 0.
    """
    return OutgoingMessage.objects.create(
        telegram_chat_id=chat_id,
        telegram_message_id=0,
        text=text,
        sent_by=user,
        reply_to_message_id=reply_to_message_id,
        reply_to_text=reply_to_text,
        topic_name=topic_name,
        status=OutgoingMessage.Status.PENDING,
        error_text="",
    )


def _update_outgoing(
    outgoing: OutgoingMessage,
    *,
    status: str,
    message_id: int = 0,
    error_text: str = "",
) -> None:
    """Update an existing OutgoingMessage with the final send result."""
    outgoing.telegram_message_id = message_id
    outgoing.status = status
    outgoing.error_text = error_text
    try:
        outgoing.save(update_fields=["telegram_message_id", "status", "error_text"])
    except Exception:
        # Запись остаётся в PENDING — аудируемая «подвисшая» попытка.
        logger.exception(
            "Failed to finalize OutgoingMessage pk=%s to status=%s; record stays PENDING",
            outgoing.pk,
            status,
        )


def send_reply(user, telegram_message: TelegramMessage, text: str) -> OutgoingMessage:
    """Reply to an incoming Telegram message from the web interface.

    The reply goes to the same chat and (for topic chats) the same topic:
    - reply_to_message_id always determines the topic of a reply;
    - message_thread_id is passed additionally only when the original message
      was received from a known topic, to guarantee the reply lands in the
      correct topic of a forum group.
    """
    normalized = _normalize_text(text)

    from telegram_bot.bot import TelegramBot

    chat_id = telegram_message.telegram_chat_id
    thread_id = telegram_message.message_thread_id
    topic_name = _topic_name_by_thread_id(thread_id)
    if not topic_name and thread_id is not None:
        # Сообщение пришло из темы, но название неизвестно в конфигурации — сохраним thread_id как метку.
        topic_name = f"тема {thread_id}"

    # Шаг 1: аудит-запись в PENDING до обращения к Telegram.
    outgoing = _create_outgoing(
        user=user,
        chat_id=chat_id,
        text=normalized,
        reply_to_message_id=telegram_message.telegram_message_id,
        reply_to_text=telegram_message.text,
        topic_name=topic_name,
    )

    # Шаг 2: вызов Telegram API.
    try:
        sent = TelegramBot().send_message(
            chat_id=chat_id,
            text=normalized,
            reply_to_message_id=telegram_message.telegram_message_id,
            message_thread_id=thread_id,
        )
    except Exception as exc:
        logger.error(
            "Failed to send reply chat_id=%s message_id=%s: %s",
            chat_id,
            telegram_message.telegram_message_id,
            type(exc).__name__,
        )
        # Шаг 4: фиксируем ошибку в той же записи, затем пробрасываем.
        _update_outgoing(
            outgoing,
            status=OutgoingMessage.Status.ERROR,
            message_id=0,
            error_text=str(exc),
        )
        raise MessagingError(str(exc)) from exc

    result = (sent or {}).get("result") or {}
    telegram_message_id = result.get("message_id") or 0

    # Шаг 3: успех — фиксируем message_id и SENT в той же записи.
    _update_outgoing(
        outgoing,
        status=OutgoingMessage.Status.SENT,
        message_id=telegram_message_id,
    )

    logger.info(
        "Sent reply chat_id=%s reply_to=%s new_message_id=%s",
        chat_id,
        telegram_message.telegram_message_id,
        telegram_message_id,
    )
    return outgoing


def send_new_message(user, text: str, thread_id: Optional[int] = None) -> OutgoingMessage:
    """Send a new message to the clan group from the web interface.

    thread_id=None sends to the general flow; a known thread_id sends to that topic.
    """
    normalized = _normalize_text(text)

    telegram_settings = TelegramSettings.objects.filter(is_active=True).first()
    chat_id = telegram_settings.group_chat_id if telegram_settings else None
    if chat_id is None:
        logger.error("No active Telegram group configured; cannot send new message")
        raise MessagingError(
            "Не настроена активная группа Telegram для отправки сообщений (Группы). "
            "Отправка новых сообщений недоступна."
        )

    from telegram_bot.bot import TelegramBot

    topic_name = _topic_name_by_thread_id(thread_id)

    # Шаг 1: аудит-запись в PENDING до обращения к Telegram.
    outgoing = _create_outgoing(
        user=user,
        chat_id=chat_id,
        text=normalized,
        reply_to_message_id=None,
        reply_to_text="",
        topic_name=topic_name,
    )

    # Шаг 2: вызов Telegram API.
    try:
        sent = TelegramBot().send_message(
            chat_id=chat_id,
            text=normalized,
            message_thread_id=thread_id,
        )
    except Exception as exc:
        logger.error(
            "Failed to send new message chat_id=%s thread_id=%s: %s",
            chat_id,
            thread_id,
            type(exc).__name__,
        )
        # Шаг 4: фиксируем ошибку в той же записи, затем пробрасываем.
        _update_outgoing(
            outgoing,
            status=OutgoingMessage.Status.ERROR,
            message_id=0,
            error_text=str(exc),
        )
        raise MessagingError(str(exc)) from exc

    result = (sent or {}).get("result") or {}
    telegram_message_id = result.get("message_id") or 0

    # Шаг 3: успех — фиксируем message_id и SENT в той же записи.
    _update_outgoing(
        outgoing,
        status=OutgoingMessage.Status.SENT,
        message_id=telegram_message_id,
    )

    logger.info(
        "Sent new message chat_id=%s thread_id=%s new_message_id=%s",
        chat_id,
        thread_id,
        telegram_message_id,
    )
    return outgoing
