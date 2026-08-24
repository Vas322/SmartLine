"""Service for mirroring schedule messages from alliance bot to clan group."""
import logging
from typing import Optional

from django.conf import settings
from django.utils import timezone

from core.models import ScheduleMirror, TelegramMessage
from telegram_bot.bot import TelegramBot, TelegramAPIError

logger = logging.getLogger(__name__)


def _bot() -> TelegramBot:
    return TelegramBot(token=settings.TELEGRAM_BOT_TOKEN)


def _default_target_chat_id() -> Optional[int]:
    """Return default target chat ID from settings or fallback to latest message chat."""
    if settings.CLAN_CHAT_ID is not None:
        return settings.CLAN_CHAT_ID
    try:
        latest = TelegramMessage.objects.latest("id")
        return latest.telegram_chat_id
    except TelegramMessage.DoesNotExist:
        return None


def _apply_to_target(
    *,
    source_chat_id: int,
    source_message_id: int,
    text: str,
    target_chat_id: Optional[int],
    alliance_bot_username: str,
    label: str,
    user,
) -> ScheduleMirror:
    """Core logic to create or update a mirrored schedule message.

    Text is NOT fetched from history. For new mirrors, text comes from
    the admin-provided parameter (for setup_mirror) or live edit (for handle_source_message).
    send_message returns message_id, not text.
    """
    if target_chat_id is None:
        target_chat_id = _default_target_chat_id()
        if target_chat_id is None:
            raise ValueError(
                "Не удалось определить целевую группу: задайте CLAN_CHAT_ID в настройках "
                "или убедитесь, что в системе есть обработанные Telegram-сообщения."
            )

    bot = _bot()

    # Try to find active mirror for exact source message
    mirror = ScheduleMirror.objects.filter(
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
        is_active=True,
    ).first()

    if mirror:
        # Existing mirror for this exact message: live edit comes with text in the update
        if mirror.last_text != text:
            try:
                bot.edit_message_text(
                    chat_id=mirror.target_chat_id,
                    message_id=mirror.target_message_id,
                    text=text,
                )
            except TelegramAPIError as exc:
                logger.exception("Failed to edit mirrored message: %s", exc)
            else:
                mirror.last_text = text
                mirror.last_synced_at = timezone.now()
                mirror.save(update_fields=["last_text", "last_synced_at", "updated_at"])
        return mirror

    # No exact match: repost the schedule text to target chat.
    # We do NOT use copy_message because Telegram blocks copying from a channel
    # (even for admins) when the channel has "Restrict saving content" enabled.
    # The text is already known from the source channel_post / admin form.
    try:
        sent = bot.send_message(chat_id=target_chat_id, text=text)
    except TelegramAPIError as exc:
        logger.exception("Failed to send mirror message: %s", exc)
        raise ValueError(
            "Не удалось отправить сообщение в группу клана. Проверьте, что бот добавлен в целевую группу "
            "и имеет право отправлять сообщения."
        )

    target_message_id = (sent.get("result") or {}).get("message_id")
    if target_message_id is None:
        raise ValueError("Telegram API не вернул message_id отправленного сообщения.")

    # ONLY AFTER successful send_message: deactivate other active mirrors for this source chat
    ScheduleMirror.objects.filter(
        source_chat_id=source_chat_id,
        is_active=True,
    ).update(is_active=False)

    # Create new active mirror with provided text (send_message returns message_id, not text)
    mirror = ScheduleMirror.objects.create(
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
        target_chat_id=target_chat_id,
        target_message_id=target_message_id,
        alliance_bot_username=alliance_bot_username,
        label=label,
        last_text=text,
        last_synced_at=timezone.now(),
        is_active=True,
        created_by=user,
    )
    return mirror


def setup_mirror(
    *,
    source_chat_id: int,
    source_message_id: int,
    target_chat_id: Optional[int],
    alliance_bot_username: str,
    label: str,
    user,
    text: str = "",
) -> ScheduleMirror:
    """Setup mirror via web form: text is provided by admin (schedule_text field).
    send_message returns message_id, not text.
    """
    return _apply_to_target(
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
        text=text,
        target_chat_id=target_chat_id,
        alliance_bot_username=alliance_bot_username,
        label=label,
        user=user,
    )


def handle_source_message(
    *,
    source_chat_id: int,
    source_message_id: int,
    text: str,
    alliance_bot_username: str,
    is_edit: bool,
) -> Optional[ScheduleMirror]:
    """Handle live message/edit from alliance bot in source chat.

    For new messages (no exact mirror): send_message creates mirror, text from live update.
    For edits (exact mirror exists): edit_message_text with live text.
    """
    if not text:
        logger.warning("Empty text for schedule mirror source message")
        return None
    try:
        return _apply_to_target(
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            text=text,
            target_chat_id=None,  # will use default
            alliance_bot_username=alliance_bot_username,
            label="",
            user=None,
        )
    except Exception as exc:
        logger.exception("Failed to mirror schedule message: %s", exc)
        try:
            from core.services.notification_service import notify_kl
            notify_kl("Smartline: ошибка при обработке сообщения с расписанием (см. логи бота).")
        except Exception:
            pass
        return None


def reconcile_all() -> dict:
    """Reconcile all active mirrors with source messages.

    Does NOT fetch from history (bot cannot read other's messages by ID).
    Best-effort: for each active mirror with non-empty last_text,
    try to edit target message to restore last known text.
    Live edits are synchronized via edited_message updates.
    Returns {"updated": int, "errors": int}.
    """
    bot = _bot()
    updated = 0
    errors = 0
    for mirror in ScheduleMirror.objects.filter(is_active=True):
        if not mirror.last_text:
            continue
        try:
            bot.edit_message_text(
                chat_id=mirror.target_chat_id,
                message_id=mirror.target_message_id,
                text=mirror.last_text,
            )
        except TelegramAPIError as exc:
            logger.error("Reconcile edit failed for mirror %s: %s", mirror, exc)
            errors += 1
        else:
            updated += 1
    return {"updated": updated, "errors": errors}


def get_current_text() -> str:
    """Get current active schedule text."""
    mirror = ScheduleMirror.objects.filter(is_active=True).first()
    return mirror.last_text if mirror else ""