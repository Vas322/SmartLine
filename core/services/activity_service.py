"""Business logic for processing Telegram messages into activities."""
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Tuple

from django.db import transaction

from core.models import Activity, Player, ProcessingError, TelegramMessage
from core.parsers import ParsedActivity, ParserError, parse_activity_message
from core.services.notification_service import (
    notify_group_reply,
    notify_processing_error,
)
from core.services.rates import payment_cast_kk, payment_kk

logger = logging.getLogger(__name__)


class ProcessResultStatus(str, Enum):
    IGNORED = "IGNORED"
    ACTIVITY_CREATED = "ACTIVITY_CREATED"
    DUPLICATE = "DUPLICATE"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    EDIT_IGNORED = "EDIT_IGNORED"


@dataclass
class ProcessResult:
    status: ProcessResultStatus
    telegram_message: Optional[TelegramMessage] = None
    activities: Optional[list] = None
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


def _adopt_nick(p: Player, nick: str) -> Tuple[Player, bool, Optional[str], bool]:
    """Update player nickname if spelling differs (case-insensitive).

    Returns (player, nick_changed, old_nickname_or_none, is_new_player).
    """
    if p.nickname.casefold() != nick.casefold():
        old = p.nickname
        p.nickname = nick
        p.save(update_fields=["nickname"])
        return p, True, old, False
    return p, False, None, False


def _resolve_player(nick: str, user_id: Optional[int]) -> Tuple[Player, bool, Optional[str], bool]:
    """Resolve a player by Telegram user_id first, then by nickname.

    - If user_id is provided and a player has that telegram_user_id, use that
      player (adopting the new nickname spelling if different).
    - Else, look up by nickname case-insensitively.
      - If found and user_id is provided but the player has a different
        telegram_user_id, raise ParserError("nick_already_bound").
      - If found and user_id is provided and the player has no telegram_user_id,
        bind it.
    - Else, create a new player with the nickname and user_id (if provided).

    Returns (player, nick_changed, old_nickname_or_none, is_new_player).
    """
    if user_id is not None:
        p = Player.objects.filter(telegram_user_id=user_id).first()
        if p is not None:
            return _adopt_nick(p, nick)

    p = Player.objects.filter(nickname__iexact=nick).order_by("id").first()
    if p is not None:
        if user_id is not None:
            if p.telegram_user_id is not None and p.telegram_user_id != user_id:
                raise ParserError("nick_already_bound")
            p.telegram_user_id = user_id
            p.save(update_fields=["telegram_user_id"])
        return _adopt_nick(p, nick)

    p = Player.objects.create(nickname=nick, telegram_user_id=user_id)
    return p, False, None, True


def _compute_payment(parsed: ParsedActivity) -> Decimal:
    """Compute the payment_kk snapshot for a parsed activity.

    Payment is the SUM of paid components: DEF pays from the DEF Rate table
    and CAST pays from the CastRate table. FARM is never paid. There is no
    multiplier anywhere.
    """
    payment = Decimal("0")
    if parsed.activity_type == "DEF":
        payment += payment_kk(parsed.wave_start, parsed.amount)
    if parsed.has_cast:
        payment += payment_cast_kk(parsed.wave_start, parsed.amount)
    return payment


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
            player, nick_changed, old_nick, is_new_player = _resolve_player(parsed.nickname, user_id)
        except ParserError as exc:
            logger.warning(
                "Player resolve error chat_id=%s message_id=%s: %s",
                chat_id,
                message_id,
                exc,
            )
            return _create_processing_error(telegram_message, str(exc))

        payment = _compute_payment(parsed)

        activity = Activity.objects.create(
            player=player,
            telegram_message=telegram_message,
            amount=parsed.amount,
            activity_type=parsed.activity_type,
            has_cast=parsed.has_cast,
            description=parsed.description,
            wave_start_time=parsed.wave_start,
            payment_kk=payment,
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

    if nick_changed:
        notify_group_reply(telegram_message, f"Ник изменён: {old_nick} → {player.nickname}")
    elif is_new_player:
        notify_group_reply(
            telegram_message,
            f"Зарегистрирован новый игрок! На {player.nickname} будет приходить оплата!",
        )

    return ProcessResult(
        status=ProcessResultStatus.ACTIVITY_CREATED,
        telegram_message=telegram_message,
        activities=[activity],
    )


def process_telegram_edit(
    *,
    chat_id: int,
    message_id: int,
    user_id: Optional[int] = None,
    username: str = "",
    text: str,
    message_date: datetime,
) -> ProcessResult:
    """Re-process an edited Telegram message without double counting.

    - If the edited text is not an activity message, the edit is ignored.
    - If the original message was never processed, treat the edit as a new
      message.
    - If the original message was already PROCESSED, the edit is ignored to
      avoid double counting.
    - If the original message was in ERROR state, delete the old error and
      re-process the edited text.
    """
    stripped = text.strip()
    if not stripped.startswith("+"):
        return ProcessResult(status=ProcessResultStatus.IGNORED)

    tm = TelegramMessage.objects.filter(
        telegram_chat_id=chat_id,
        telegram_message_id=message_id,
    ).first()
    if tm is None:
        return process_telegram_message(
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            username=username,
            text=text,
            message_date=message_date,
        )

    # уже засчитано -> не пересчитывать
    if tm.status == TelegramMessage.Status.PROCESSED:
        notify_group_reply(tm, "Сообщение уже учтено — правка игнорируется.")
        return ProcessResult(
            status=ProcessResultStatus.EDIT_IGNORED,
            telegram_message=tm,
        )

    # было ERROR -> переобработать
    with transaction.atomic():
        ProcessingError.objects.filter(telegram_message=tm).delete()
        tm.text = stripped
        tm.message_date = message_date
        try:
            parsed = parse_activity_message(stripped)
        except ParserError as exc:
            tm.status = TelegramMessage.Status.ERROR
            tm.save(update_fields=["text", "message_date", "status"])
            return _create_processing_error(tm, str(exc))

        try:
            player, nick_changed, old_nick, is_new_player = _resolve_player(parsed.nickname, user_id)
        except ParserError as exc:
            tm.status = TelegramMessage.Status.ERROR
            tm.save(update_fields=["text", "message_date", "status"])
            return _create_processing_error(tm, str(exc))

        payment = _compute_payment(parsed)

        Activity.objects.create(
            player=player,
            telegram_message=tm,
            amount=parsed.amount,
            activity_type=parsed.activity_type,
            has_cast=parsed.has_cast,
            description=parsed.description,
            wave_start_time=parsed.wave_start,
            payment_kk=payment,
        )
        tm.status = TelegramMessage.Status.PROCESSED
        tm.save(update_fields=["status", "text", "message_date"])

    if nick_changed:
        notify_group_reply(tm, f"Ник изменён: {old_nick} → {player.nickname}")
    elif is_new_player:
        notify_group_reply(
            tm,
            f"Зарегистрирован новый игрок! На {player.nickname} будет приходить оплата!",
        )

    return ProcessResult(
        status=ProcessResultStatus.ACTIVITY_CREATED,
        telegram_message=tm,
        activities=(
            list(Activity.objects.filter(telegram_message=tm))
        ),
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