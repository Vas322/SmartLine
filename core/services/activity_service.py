"""Business logic for processing Telegram messages into activities."""
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Tuple

from django.db import transaction
from django.utils import timezone

from core.models import Activity, Player, ProcessingError, Registration, TelegramMessage
from core.parsers import (
    ParsedActivity,
    ParsedRegistration,
    ParserError,
    parse_activity_message,
    parse_registration_message,
)
from core.services.notification_service import (
    notify_group_reply,
    notify_processing_error,
)
from core.services.rates import payment_cast_kk, payment_kk, registration_payment_kk

logger = logging.getLogger(__name__)


class ProcessResultStatus(str, Enum):
    IGNORED = "IGNORED"
    ACTIVITY_CREATED = "ACTIVITY_CREATED"
    DUPLICATE = "DUPLICATE"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    EDIT_IGNORED = "EDIT_IGNORED"
    EDIT_ACCEPTED = "EDIT_ACCEPTED"
    NICK_MISMATCH = "NICK_MISMATCH"
    REGISTRATION_CREATED = "REGISTRATION_CREATED"
    VALIDATION_ERROR = "VALIDATION_ERROR"


@dataclass
class ProcessResult:
    status: ProcessResultStatus
    telegram_message: Optional[TelegramMessage] = None
    activities: Optional[list] = None
    processing_error: Optional[ProcessingError] = None
    changes_text: Optional[str] = None


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


def _adopt_nick(p: Player, nick: str) -> Tuple[Player, bool, Optional[str], bool, bool]:
    """Update player nickname if spelling differs (case-insensitive).

    Returns (player, nick_changed, old_nickname_or_none, is_new_player, mismatch).
    """
    if p.nickname.casefold() != nick.casefold():
        old = p.nickname
        p.nickname = nick
        p.save(update_fields=["nickname"])
        return p, True, old, False, False
    return p, False, None, False, False


def _resolve_player(nick: str, user_id: Optional[int]) -> Tuple[Player, bool, Optional[str], bool, bool]:
    """Resolve a player by Telegram user_id first, then by nickname.

    - If user_id is provided and a player has that telegram_user_id, use that
      player. If the written nick differs from the registered one (typo),
      mismatch=True is returned; the nick is NOT changed.
    - Else, look up by nickname case-insensitively.
      - If found and user_id is provided but the player has a different
        telegram_user_id, raise ParserError("nick_already_bound").
      - If found and user_id is provided and the player has no telegram_user_id,
        bind it and return via _adopt_nick (5-tuple).
    - Else, create a new player with the nickname and user_id (if provided)
      using get_or_create to avoid IntegrityError on race conditions.

    Returns (player, nick_changed, old_nickname_or_none, is_new_player, mismatch).
    """
    if user_id is not None:
        p = Player.objects.filter(telegram_user_id=user_id).first()
        if p is not None:
            mismatch = p.nickname.casefold() != nick.casefold()
            return p, False, None, False, mismatch

    p = Player.objects.filter(nickname__iexact=nick).order_by("id").first()
    if p is not None:
        if user_id is not None:
            if p.telegram_user_id is not None and p.telegram_user_id != user_id:
                raise ParserError("nick_already_bound")
            p.telegram_user_id = user_id
            p.save(update_fields=["telegram_user_id"])
        return _adopt_nick(p, nick)

    # Use get_or_create to avoid IntegrityError on unique nickname constraint
    p, created = Player.objects.get_or_create(
        nickname=nick,
        defaults={"telegram_user_id": user_id},
    )
    return p, False, None, created, False


def _nick_mismatch_text(username: str, correct_nick: str) -> str:
    """Generate warning text for nickname mismatch."""
    if username:
        return (
            f"Возможно вы ошиблись ником, за пользователем @{username} "
            f"зарегистрирован {correct_nick}. Исправь ник в сообщении."
        )
    return (
        f"Возможно вы ошиблись ником, за вами зарегистрирован {correct_nick}. "
        f"Исправь ник в сообщении."
    )


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
    message_thread_id: Optional[int] = None,
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
            player, nick_changed, old_nick, is_new_player, mismatch = _resolve_player(parsed.nickname, user_id)
        except ParserError as exc:
            logger.warning(
                "Player resolve error chat_id=%s message_id=%s: %s",
                chat_id,
                message_id,
                exc,
            )
            return _create_processing_error(telegram_message, str(exc))

        if mismatch:
            telegram_message.status = TelegramMessage.Status.ERROR
            telegram_message.save(update_fields=["status"])
            notify_group_reply(
                telegram_message,
                _nick_mismatch_text(username, player.nickname),
                message_thread_id=message_thread_id,
            )
            return ProcessResult(
                status=ProcessResultStatus.NICK_MISMATCH,
                telegram_message=telegram_message,
            )

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
    message_thread_id: Optional[int] = None,
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
            message_thread_id=message_thread_id,
        )

    # уже засчитано -> пересчитать с учётом правок
    if tm.status == TelegramMessage.Status.PROCESSED:
        # Парсим новый текст
        try:
            parsed = parse_activity_message(stripped)
        except ParserError as exc:
            logger.warning("Edit parse error chat_id=%s message_id=%s: %s", chat_id, message_id, exc)
            return _create_processing_error(tm, str(exc))

        # Находим существующую Activity (внутри транзакции, с блокировкой строки)
        with transaction.atomic():
            activity = Activity.objects.select_for_update().filter(telegram_message=tm).first()
            if activity is None:
                # Fallback: создаём как при ERROR->PROCESSED (resolve player, compute, create)
                try:
                    player, nick_changed, old_nick, is_new_player, mismatch = _resolve_player(parsed.nickname, user_id)
                except ParserError as exc:
                    return _create_processing_error(tm, str(exc))
                if mismatch:
                    tm.status = TelegramMessage.Status.ERROR
                    tm.save(update_fields=["status"])
                    notify_group_reply(tm, _nick_mismatch_text(username, player.nickname), message_thread_id=message_thread_id)
                    return ProcessResult(status=ProcessResultStatus.NICK_MISMATCH, telegram_message=tm)
                payment = _compute_payment(parsed)
                activity = Activity.objects.create(
                    player=player, telegram_message=tm, amount=parsed.amount,
                    activity_type=parsed.activity_type, has_cast=parsed.has_cast,
                    description=parsed.description, wave_start_time=parsed.wave_start, payment_kk=payment,
                )
                tm.status = TelegramMessage.Status.PROCESSED
                tm.save(update_fields=["status"])
                if nick_changed:
                    notify_group_reply(tm, f"Ник изменён: {old_nick} → {player.nickname}")
                elif is_new_player:
                    notify_group_reply(tm, f"Зарегистрирован новый игрок! На {player.nickname} будет приходить оплата!")
                return ProcessResult(status=ProcessResultStatus.ACTIVITY_CREATED, telegram_message=tm, activities=[activity])

            # Проверка ника на правке: несовпадение -> уведомить, NICK_MISMATCH.
            # Activity и tm.status НЕ меняются, т.к. Activity уже валидна и засчитана.
            try:
                player, nick_changed, old_nick, is_new_player, mismatch = _resolve_player(parsed.nickname, user_id)
            except ParserError as exc:
                return _create_processing_error(tm, str(exc))
            if mismatch:
                notify_group_reply(tm, _nick_mismatch_text(username, player.nickname), message_thread_id=message_thread_id)
                return ProcessResult(status=ProcessResultStatus.NICK_MISMATCH, telegram_message=tm)

            # Сравниваем и собираем изменения.
            # Тип активности и признак каста объединяем в одну человекочитаемую
            # метку "TYPE[+каст]", чтобы правка показывала "было -> стало" целиком.
            changes = []
            old_label = f"{activity.activity_type}{'+CAST' if activity.has_cast else ''}"
            new_label = f"{parsed.activity_type}{'+CAST' if parsed.has_cast else ''}"
            if old_label != new_label:
                changes.append(f"активность {old_label} → {new_label}")
            if activity.amount != parsed.amount:
                changes.append(f"время на волне {activity.amount} → {parsed.amount}")
            if activity.wave_start_time != parsed.wave_start:
                old_t = activity.wave_start_time.strftime("%H:%M") if activity.wave_start_time else "—"
                new_t = parsed.wave_start.strftime("%H:%M")
                changes.append(f"начало волны {old_t} → {new_t}")

            if not changes:
                return ProcessResult(status=ProcessResultStatus.EDIT_IGNORED, telegram_message=tm)

            if tm.edit_count == 0:
                tm.original_text = tm.text
            tm.edit_history.append(tm.text)
            tm.text = stripped
            tm.edit_count += 1
            tm.message_date = message_date
            tm.save(update_fields=["text", "original_text", "edit_history", "edit_count", "message_date"])

            activity.activity_type = parsed.activity_type
            activity.amount = parsed.amount
            activity.has_cast = parsed.has_cast
            activity.wave_start_time = parsed.wave_start
            activity.payment_kk = _compute_payment(parsed)
            activity.edited_at = timezone.now()
            activity.save(update_fields=[
                "activity_type", "amount", "has_cast", "wave_start_time", "payment_kk", "edited_at",
            ])

        changes_text = "; ".join(changes)
        logger.info("Activity edit accepted chat_id=%s message_id=%s changes=%s", chat_id, message_id, changes_text)
        return ProcessResult(
            status=ProcessResultStatus.EDIT_ACCEPTED,
            telegram_message=tm,
            activities=[activity],
            changes_text=changes_text,
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
            player, nick_changed, old_nick, is_new_player, mismatch = _resolve_player(parsed.nickname, user_id)
        except ParserError as exc:
            tm.status = TelegramMessage.Status.ERROR
            tm.save(update_fields=["text", "message_date", "status"])
            return _create_processing_error(tm, str(exc))

        if mismatch:
            tm.status = TelegramMessage.Status.ERROR
            tm.save(update_fields=["text", "message_date", "status"])
            notify_group_reply(
                tm,
                _nick_mismatch_text(username, player.nickname),
                message_thread_id=message_thread_id,
            )
            return ProcessResult(
                status=ProcessResultStatus.NICK_MISMATCH,
                telegram_message=tm,
            )

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


def _resolve_registration_player(user_id: Optional[int]) -> Tuple[Player, bool, Optional[str], bool, bool]:
    """Resolve a player for registration by Telegram user_id only.

    Registration messages don't contain a nickname, so we only match by user_id.
    Returns (player, nick_changed, old_nickname_or_none, is_new_player, mismatch).
    For registration, mismatch is always False (we don't create players automatically).
    """
    if user_id is None:
        return None, False, None, False, False  # type: ignore[return-value]

    p = Player.objects.filter(telegram_user_id=user_id).first()
    if p is not None:
        return p, False, None, False, False

    # No player with this user_id - registration not allowed
    return None, False, None, False, False  # type: ignore[return-value]


def _create_registration_error(
    telegram_message: TelegramMessage,
    reason: str,
    message_thread_id: Optional[int] = None,
) -> ProcessResult:
    """Create a processing error for registration and send group reply."""
    telegram_message.status = TelegramMessage.Status.ERROR
    telegram_message.save(update_fields=["status"])

    error = ProcessingError.objects.create(
        telegram_message=telegram_message,
        reason=reason,
        status=ProcessingError.Status.NEW,
    )

    # Send user-friendly message to group
    from core.error_messages import friendly_error_message
    sent = notify_group_reply(
        telegram_message,
        friendly_error_message(reason),
        message_thread_id=message_thread_id,
    )
    if sent:
        error.status = ProcessingError.Status.NOTIFIED
        error.save(update_fields=["status"])

    return ProcessResult(
        status=ProcessResultStatus.VALIDATION_ERROR if reason in ("registration_no_screenshot", "registration_unregistered_sender") else ProcessResultStatus.PROCESSING_ERROR,
        telegram_message=telegram_message,
        processing_error=error,
    )


def process_registration_message(
    *,
    chat_id: int,
    message_id: int,
    user_id: Optional[int] = None,
    username: str = "",
    text: str,
    message_date: datetime,
    has_photo: bool,
    photo_file_id: Optional[str] = None,
    message_thread_id: Optional[int] = None,
) -> ProcessResult:
    """Process a Telegram message as a clan fort registration."""
    stripped = text.strip()

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
                status=ProcessResultStatus.EDIT_IGNORED,
                telegram_message=telegram_message,
            )

        # Parse registration message
        try:
            parsed = parse_registration_message(stripped)
        except ParserError as exc:
            logger.warning(
                "Registration parser error chat_id=%s message_id=%s: %s",
                chat_id,
                message_id,
                exc,
            )
            return _create_registration_error(telegram_message, str(exc), message_thread_id)

        logger.info(
            "Parsed registration chat_id=%s message_id=%s clans_count=%s",
            chat_id,
            message_id,
            parsed.clans_count,
        )

        # Check for photo
        if not has_photo:
            logger.warning(
                "Registration without photo chat_id=%s message_id=%s",
                chat_id,
                message_id,
            )
            return _create_registration_error(
                telegram_message,
                "registration_no_screenshot",
                message_thread_id,
            )

        # Resolve player by user_id only
        player, _, _, _, _ = _resolve_registration_player(user_id)
        if player is None:
            logger.warning(
                "Unregistered sender for registration chat_id=%s message_id=%s user_id=%s",
                chat_id,
                message_id,
                user_id,
            )
            return _create_registration_error(
                telegram_message,
                "registration_unregistered_sender",
                message_thread_id,
            )

        # Calculate payment
        payment_kk = registration_payment_kk(message_date.time(), parsed.clans_count)

        # Create registration
        registration = Registration.objects.create(
            player=player,
            telegram_message=telegram_message,
            clans_count=parsed.clans_count,
            payment_kk=payment_kk,
            description=parsed.description,
            photo_file_id=photo_file_id,
            registered_at=message_date,
        )

        telegram_message.status = TelegramMessage.Status.PROCESSED
        telegram_message.save(update_fields=["status"])

        logger.info(
            "Registration created chat_id=%s message_id=%s player=%s clans=%s payment=%s",
            chat_id,
            message_id,
            player.nickname,
            parsed.clans_count,
            payment_kk,
        )

    return ProcessResult(
        status=ProcessResultStatus.REGISTRATION_CREATED,
        telegram_message=telegram_message,
        activities=[registration],
    )


def process_registration_edit(
    *,
    chat_id: int,
    message_id: int,
    user_id: Optional[int] = None,
    username: str = "",
    text: str,
    message_date: datetime,
    has_photo: bool,
    photo_file_id: Optional[str] = None,
    message_thread_id: Optional[int] = None,
) -> ProcessResult:
    """Re-process an edited Telegram registration message without double counting."""
    stripped = text.strip()

    tm = TelegramMessage.objects.filter(
        telegram_chat_id=chat_id,
        telegram_message_id=message_id,
    ).first()

    if tm is None:
        return process_registration_message(
            chat_id=chat_id,
            message_id=message_id,
            user_id=user_id,
            username=username,
            text=text,
            message_date=message_date,
            has_photo=has_photo,
            photo_file_id=photo_file_id,
            message_thread_id=message_thread_id,
        )

    # уже засчитано -> не пересчитывать
    if tm.status == TelegramMessage.Status.PROCESSED:
        # Check if it was a registration
        if hasattr(tm, "registration") and tm.registration is not None:
            notify_group_reply(tm, "Регистрация уже учтена — правка игнорируется.")
        else:
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

        # Parse registration message
        try:
            parsed = parse_registration_message(stripped)
        except ParserError as exc:
            tm.status = TelegramMessage.Status.ERROR
            tm.save(update_fields=["text", "message_date", "status"])
            logger.warning(
                "Registration edit parser error chat_id=%s message_id=%s: %s",
                chat_id,
                message_id,
                exc,
            )
            return _create_registration_error(tm, str(exc), message_thread_id)

        # Check for photo
        if not has_photo:
            tm.status = TelegramMessage.Status.ERROR
            tm.save(update_fields=["text", "message_date", "status"])
            return _create_registration_error(
                tm,
                "registration_no_screenshot",
                message_thread_id,
            )

        # Resolve player by user_id only
        player, _, _, _, _ = _resolve_registration_player(user_id)
        if player is None:
            tm.status = TelegramMessage.Status.ERROR
            tm.save(update_fields=["text", "message_date", "status"])
            return _create_registration_error(
                tm,
                "registration_unregistered_sender",
                message_thread_id,
            )

        # Calculate payment
        payment_kk = registration_payment_kk(message_date.time(), parsed.clans_count)

        # Create registration
        Registration.objects.create(
            player=player,
            telegram_message=tm,
            clans_count=parsed.clans_count,
            payment_kk=payment_kk,
            description=parsed.description,
            photo_file_id=photo_file_id,
            registered_at=message_date,
        )

        tm.status = TelegramMessage.Status.PROCESSED
        tm.save(update_fields=["status", "text", "message_date"])

        logger.info(
            "Registration created (edit) chat_id=%s message_id=%s player=%s clans=%s payment=%s",
            chat_id,
            message_id,
            player.nickname,
            parsed.clans_count,
            payment_kk,
        )

    return ProcessResult(
        status=ProcessResultStatus.REGISTRATION_CREATED,
        telegram_message=tm,
        activities=list(Registration.objects.filter(telegram_message=tm)),
    )