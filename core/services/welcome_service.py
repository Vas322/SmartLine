"""Business logic for greeting new Telegram group members.

On the first join (new_chat_members) a Player is auto-created with
nickname=None, telegram_user_id and telegram_username; on re-join an
existing inactive Player is reactivated (created_at is not touched). A
welcome message is sent once per join event (reply to the join message),
subject to anti-spam rules (mass join / active block). On leaving
(left_chat_member) the Player is deactivated.
"""
import logging
from datetime import timedelta
from typing import Optional

from django.db import IntegrityError
from django.utils import timezone

from core.models import OutgoingMessage, Player, WelcomeSettings

logger = logging.getLogger(__name__)

MASS_JOIN_THRESHOLD = 3  # более 3 (т.е. 4+) новых за минуту = массовый заход
BLOCK_MINUTES = 15


def get_welcome_settings() -> WelcomeSettings:
    """Return the singleton WelcomeSettings (always works with pk=1)."""
    settings_obj, _ = WelcomeSettings.objects.get_or_create(pk=1)
    return settings_obj


def _ensure_player(*, user_id: int, username: str) -> tuple[Player, bool]:
    """Create or activate a Player for a joining member.

    Returns (player, created) where created is True only when a brand-new
    Player was created in this call. Re-activation of an existing inactive
    Player does not touch created_at/nickname and returns created=False.
    """
    player = Player.objects.filter(telegram_user_id=user_id).first()
    if player is not None:
        if not player.is_active:
            player.is_active = True
            player.save(update_fields=["is_active", "updated_at"])
            logger.info(
                "Player reactivated telegram_user_id=%s player_id=%s",
                user_id,
                player.pk,
            )
        return player, False

    try:
        player = Player.objects.create(
            nickname=None,
            telegram_user_id=user_id,
            telegram_username=username or "",
            is_active=True,
        )
    except IntegrityError:
        # Редкий гонки: дубликат telegram_user_id создан конкурентно — берём его.
        player = Player.objects.filter(telegram_user_id=user_id).first()
        return player, False
    logger.info(
        "Player created (welcome) telegram_user_id=%s player_id=%s",
        user_id,
        player.pk,
    )
    return player, True


def _record_outgoing_and_send(
    *,
    chat_id: int,
    text: str,
    reply_to_message_id: int,
    message_thread_id: Optional[int],
) -> None:
    """Audit an outgoing welcome in OutgoingMessage and send it via Telegram.

    The audit record is created in PENDING before the API call, then
    finalised to SENT/ERROR so every attempt is auditable.
    """
    outgoing = OutgoingMessage.objects.create(
        telegram_chat_id=chat_id,
        telegram_message_id=0,
        text=text,
        sent_by=None,
        reply_to_message_id=reply_to_message_id,
        reply_to_text="",
        topic_name="",
        status=OutgoingMessage.Status.PENDING,
        error_text="",
        source=OutgoingMessage.Source.WELCOME,
    )

    from telegram_bot.bot import TelegramBot

    try:
        sent = TelegramBot().send_message(
            chat_id=chat_id,
            text=text,
            reply_to_message_id=reply_to_message_id,
            message_thread_id=message_thread_id,
        )
    except Exception as exc:
        outgoing.status = OutgoingMessage.Status.ERROR
        outgoing.error_text = str(exc)
        outgoing.save(update_fields=["status", "error_text"])
        logger.error(
            "Failed to send welcome chat_id=%s reply_to=%s: %s",
            chat_id,
            reply_to_message_id,
            type(exc).__name__,
        )
        return

    result = (sent or {}).get("result") or {}
    outgoing.telegram_message_id = result.get("message_id") or 0
    outgoing.status = OutgoingMessage.Status.SENT
    outgoing.save(update_fields=["telegram_message_id", "status"])


def handle_new_chat_members(
    *,
    chat_id: int,
    message_id: int,
    new_members: list[dict],
    message_thread_id: Optional[int] = None,
) -> None:
    """Process a new_chat_members event: create/activate Players and greet.

    Sends a welcome message once per event if allowed by anti-spam rules.
    All logic is wrapped so one bad event never breaks other events.
    """
    try:
        if not new_members:
            return

        settings_obj = get_welcome_settings()

        new_count_this_call = 0
        for member in new_members:
            user_id = member.get("id")
            if user_id is None:
                continue
            username = member.get("username", "") or ""
            _player, created = _ensure_player(user_id=user_id, username=username)
            if created:
                new_count_this_call += 1

        now = timezone.now()
        # Новых за последнюю минуту (включая только что созданных в этом вызове).
        new_last_minute = Player.objects.filter(
            created_at__gte=now - timedelta(minutes=1)
        ).count()

        mass_join = new_last_minute > MASS_JOIN_THRESHOLD
        if mass_join:
            settings_obj.block_until = now + timedelta(minutes=BLOCK_MINUTES)
            settings_obj.save(update_fields=["block_until", "updated_at"])
            logger.info(
                "Mass join detected chat_id=%s new_last_minute=%s block_until=%s",
                chat_id,
                new_last_minute,
                settings_obj.block_until,
            )

        welcome_text = settings_obj.welcome_text.strip()
        blocked = settings_obj.block_until is not None and settings_obj.block_until > now

        # Приветствуем ТОЛЬКО новых участников (в событии есть вновь созданный
        # Player). Повторно вошедшие (реактивация) приветствие не получают.
        send_welcome = (
            new_count_this_call > 0
            and bool(welcome_text)
            and not blocked
            and not mass_join
        )
        if send_welcome:
            _record_outgoing_and_send(
                chat_id=chat_id,
                text=welcome_text,
                reply_to_message_id=message_id,
                message_thread_id=message_thread_id,
            )
            logger.info(
                "Welcome sent chat_id=%s message_id=%s members=%s",
                chat_id,
                message_id,
                len(new_members),
            )
        else:
            logger.info(
                "Welcome skipped chat_id=%s message_id=%s mass_join=%s blocked=%s",
                chat_id,
                message_id,
                mass_join,
                blocked,
            )

        logger.info(
            "handle_new_chat_members chat_id=%s members=%s created_this_call=%s",
            chat_id,
            len(new_members),
            new_count_this_call,
        )
    except Exception:
        logger.exception("Failed to handle new chat members event")


def handle_left_chat_member(*, user_id: int) -> None:
    """Deactivate a Player when a member leaves the group.

    History is preserved (Player is hidden but not deleted). If no Player is
    found, just log it.
    """
    try:
        player = Player.objects.filter(telegram_user_id=user_id).first()
        if player is None:
            logger.info("left_chat_member without player user_id=%s", user_id)
            return
        player.is_active = False
        player.save(update_fields=["is_active", "updated_at"])
        logger.info(
            "Player deactivated (left group) telegram_user_id=%s player_id=%s",
            user_id,
            player.pk,
        )
    except Exception:
        logger.exception("Failed to handle left chat member event")


def reset_block_until() -> None:
    """Clear the welcome block (manual reset from the web interface)."""
    settings_obj = get_welcome_settings()
    if settings_obj.block_until is not None:
        settings_obj.block_until = None
        settings_obj.save(update_fields=["block_until", "updated_at"])
        logger.info("Welcome block reset manually")
