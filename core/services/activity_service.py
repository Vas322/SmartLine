"""Business logic for processing Telegram messages into activities."""
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Tuple

from django.db import transaction

from core.models import Activity, Player, ProcessingError, TelegramMessage
from core.parsers import ParserError, parse_activity_message
from core.services.notification_service import notify_processing_error

logger = logging.getLogger(__name__)


class ProcessResultStatus(str, Enum):
    IGNORED = "IGNORED"
    ACTIVITY_CREATED = "ACTIVITY_CREATED"
    DUPLICATE = "DUPLICATE"
    PROCESSING_ERROR = "PROCESSING_ERROR"


@dataclass
class ProcessResult:
    status: ProcessResultStatus
    telegram_message: Optional[TelegramMessage] = None
    activity: Optional[Activity] = None
    processing_error: Optional[ProcessingError] = None


def get_or_create_telegram_message(
    *,
    chat_id: int,
    message_id: int,
    defaults: dict,
) -> Tuple[TelegramMessage, bool]:
    """Get or create a TelegramMessage, relying on the DB uniqueness."""
    return TelegramMessage.objects.get_or_create(
        telegram_chat_id=chat_id,
        telegram_message_id=message_id,
        defaults=defaults,
    )


class PlayerConflictError(Exception):
    """Raised when a nickname is already bound to another Telegram user."""


def _resolve_or_create_player(
    nickname: str,
    user_id: Optional[int],
    username: str,
) -> Tuple[Player, bool]:
    """Return a Player for the nickname, auto-creating it on first use.

    Binding rules:
    - No player with this nickname (case-insensitive) yet: create one bound to
      the sender, keeping the nickname spelling as provided.
    - Player exists but is unbound: bind it to the current sender.
    - Player exists and is bound to the current sender: reuse it.
    - Player exists and is bound to another Telegram user: raise PlayerConflict.

    Nicknames are matched case-insensitively (POCOMAXA and pocomaxa are the
    same player), but the stored spelling is the one first seen.

    Returns (player, created).
    """
    player = Player.objects.filter(nickname__iexact=nickname).order_by("id").first()
    if player is None:
        player = Player.objects.create(
            nickname=nickname,
            telegram_user_id=user_id,
            telegram_username=username,
        )
        logger.info("Player auto-created nickname=%s user_id=%s", nickname, user_id)
        return player, True

    if player.telegram_user_id is None:
        player.telegram_user_id = user_id
        player.telegram_username = username
        player.save(update_fields=["telegram_user_id", "telegram_username", "updated_at"])
        logger.info("Player bound nickname=%s user_id=%s", nickname, user_id)
        return player, False

    if player.telegram_user_id != user_id:
        raise PlayerConflictError(
            f"nickname_registered_to_other_telegram:{nickname}"
        )

    return player, False


def process_telegram_message(
    *,
    chat_id: int,
    message_id: int,
    user_id: Optional[int] = None,
    username: str = "",
    text: str,
    message_date: datetime,
) -> ProcessResult:
    """Process a single Telegram message into an Activity or an error record."""
    stripped = text.strip()
    if not stripped.startswith("+"):
        logger.info(
            "Ignoring non-activity message chat_id=%s message_id=%s",
            chat_id,
            message_id,
        )
        return ProcessResult(status=ProcessResultStatus.IGNORED)

    defaults = {
        "telegram_user_id": user_id,
        "telegram_username": username,
        "text": stripped,
        "message_date": message_date,
    }

    with transaction.atomic():
        telegram_message, created = get_or_create_telegram_message(
            chat_id=chat_id,
            message_id=message_id,
            defaults=defaults,
        )
        if not created:
            logger.info(
                "Duplicate telegram message chat_id=%s message_id=%s",
                chat_id,
                message_id,
            )
            return ProcessResult(
                status=ProcessResultStatus.DUPLICATE,
                telegram_message=telegram_message,
            )

        try:
            parsed = parse_activity_message(stripped)
        except ParserError as exc:
            logger.warning(
                "Parser error chat_id=%s message_id=%s: %s",
                chat_id,
                message_id,
                exc,
            )
            return _create_processing_error(telegram_message, str(exc))

        logger.info(
            "Parsed message chat_id=%s message_id=%s amount=%s type=%s",
            chat_id,
            message_id,
            parsed.amount,
            parsed.activity_type,
        )

        try:
            player, _created = _resolve_or_create_player(
                parsed.nickname,
                user_id=user_id,
                username=username,
            )
        except PlayerConflictError as exc:
            logger.warning(
                "Player nickname conflict chat_id=%s message_id=%s: %s",
                chat_id,
                message_id,
                exc,
            )
            return _create_processing_error(telegram_message, str(exc))

        activity = Activity.objects.create(
            player=player,
            telegram_message=telegram_message,
            amount=parsed.amount,
            activity_type=parsed.activity_type,
            description=parsed.description,
        )
        telegram_message.status = TelegramMessage.Status.PROCESSED
        telegram_message.save(update_fields=["status"])

        logger.info(
            "Activity created chat_id=%s message_id=%s player=%s amount=%s type=%s",
            chat_id,
            message_id,
            player.nickname,
            parsed.amount,
            parsed.activity_type,
        )
        return ProcessResult(
            status=ProcessResultStatus.ACTIVITY_CREATED,
            telegram_message=telegram_message,
            activity=activity,
        )


def _create_processing_error(
    telegram_message: TelegramMessage,
    reason: str,
) -> ProcessResult:
    telegram_message.status = TelegramMessage.Status.ERROR
    telegram_message.save(update_fields=["status"])

    error = ProcessingError.objects.create(
        telegram_message=telegram_message,
        reason=reason,
        status=ProcessingError.Status.NEW,
    )
    notify_processing_error(error)
    return ProcessResult(
        status=ProcessResultStatus.PROCESSING_ERROR,
        telegram_message=telegram_message,
        processing_error=error,
    )
