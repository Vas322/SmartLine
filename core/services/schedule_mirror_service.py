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
    """Core logic to create or update a mirrored schedule message."""
    if target_chat_id is None:
        target_chat_id = _default_target_chat_id()
        if target_chat_id is None:
            raise ValueError("Target chat ID is not configured and no messages exist to infer it.")

    bot = _bot()

    # Try to find active mirror for exact source message
    mirror = ScheduleMirror.objects.filter(
        source_chat_id=source_chat_id,
        source_message_id=source_message_id,
        is_active=True,
    ).first()

    if mirror:
        # Existing mirror for this exact message
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

    # No exact match: deactivate all active mirrors for this source chat (switch to new schedule)
    ScheduleMirror.objects.filter(
        source_chat_id=source_chat_id,
        is_active=True,
    ).update(is_active=False)

    # Copy message to target chat
    try:
        copy_result = bot.copy_message(
            chat_id=target_chat_id,
            from_chat_id=source_chat_id,
            from_message_id=source_message_id,
        )
    except TelegramAPIError as exc:
        logger.exception("Failed to copy schedule message: %s", exc)
        raise ValueError("Не удалось скопировать сообщение. Проверьте ID и что бот состоит в группах.") from exc

    target_message_id = copy_result.get("result", {}).get("message_id")
    if target_message_id is None:
        raise ValueError("Telegram API не вернул message_id скопированного сообщения.")

    # Create new active mirror
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
) -> ScheduleMirror:
    """Setup mirror via web form: fetch message text first, then apply."""
    bot = _bot()
    try:
        msg_data = bot.get_message(source_chat_id, source_message_id)
    except TelegramAPIError as exc:
        logger.exception("Failed to get source message: %s", exc)
        raise ValueError("Не удалось получить сообщение по указанному ID. Проверьте ID и что бот состоит в группе.") from exc

    text = msg_data.get("result", {}).get("text", "")
    if not text:
        raise ValueError("Сообщение не содержит текста.")

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
    """Handle live message/edit from alliance bot in source chat."""
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
        return None


def reconcile_all() -> None:
    """Reconcile all active mirrors with source messages."""
    bot = _bot()
    for mirror in ScheduleMirror.objects.filter(is_active=True):
        try:
            msg_data = bot.get_message(mirror.source_chat_id, mirror.source_message_id)
        except TelegramAPIError as exc:
            logger.warning("Reconcile failed for mirror %s: %s", mirror, exc)
            continue

        text = msg_data.get("result", {}).get("text", "")
        if text and mirror.last_text != text:
            try:
                bot.edit_message_text(
                    chat_id=mirror.target_chat_id,
                    message_id=mirror.target_message_id,
                    text=text,
                )
            except TelegramAPIError as exc:
                logger.warning("Reconcile edit failed for mirror %s: %s", mirror, exc)
                continue
            mirror.last_text = text
            mirror.last_synced_at = timezone.now()
            mirror.save(update_fields=["last_text", "last_synced_at", "updated_at"])


def get_current_text() -> str:
    """Get current active schedule text."""
    mirror = ScheduleMirror.objects.filter(is_active=True).first()
    return mirror.last_text if mirror else ""