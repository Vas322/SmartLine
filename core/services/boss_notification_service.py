"""Business logic for Telegram notifications about Epic RB respawns."""
import logging
from datetime import date, datetime, timezone as dt_timezone

from django.db import IntegrityError, transaction
from django.utils import timezone
from zoneinfo import ZoneInfo

from core.models import (
    BossRespawn,
    DEFAULT_BOSS_TEMPLATE,
    EpicBossNotificationLog,
    EpicBossNotificationSettings,
)
from core.services import messaging_service

logger = logging.getLogger(__name__)

MSK_TZ = ZoneInfo("Europe/Moscow")


def get_settings() -> EpicBossNotificationSettings:
    """Return the singleton EpicBossNotificationSettings (pk=1)."""
    settings_obj, _ = EpicBossNotificationSettings.objects.get_or_create(pk=1)
    return settings_obj


def should_notify_today(today: date | None = None) -> bool:
    """Return True if no notification has been sent yet today (MSK)."""
    today = today or timezone.localdate()
    return not EpicBossNotificationLog.objects.filter(notify_date=today).exists()


def _boss_line(boss: BossRespawn) -> str:
    """Одна строка босса для сообщения: «Имя — с ЧЧ:ММ до ЧЧ:ММ МСК»."""
    start_msk = boss.respawn_start.astimezone(MSK_TZ)
    end_msk = boss.respawn_end.astimezone(MSK_TZ)
    return f"{boss.boss_name} — с {start_msk:%H:%M} до {end_msk:%H:%M} МСК"


def get_bosses_for_notification() -> list[BossRespawn]:
    """Выбранные в настройках боссы (любого типа), респающие сегодня (МСК)."""
    settings_obj = get_settings()
    selected = settings_obj.selected_bosses or []
    today = timezone.now().astimezone(MSK_TZ).date()
    return [
        b
        for b in BossRespawn.objects.filter(boss_name__in=selected)
        .order_by("respawn_start")
        if b.respawn_start.astimezone(MSK_TZ).date() == today
    ]


def _demo_boss() -> BossRespawn:
    """Демо-босс для примера сообщения (Antharas, 21:07 МСК)."""
    demo_utc = datetime(2026, 1, 1, 18, 7, tzinfo=dt_timezone.utc)
    return BossRespawn(
        boss_name="Antharas",
        boss_type=BossRespawn.BossType.EPIC,
        respawn_start=demo_utc,
        respawn_end=demo_utc,
    )


def generate_notification_text(bosses) -> str:
    """Подставить {bosses} в шаблон: строки «Имя — с ЧЧ:ММ до ЧЧ:ММ МСК»."""
    settings_obj = get_settings()
    template = (settings_obj.text_template or "").strip() or DEFAULT_BOSS_TEMPLATE
    lines = "\n".join(_boss_line(b) for b in bosses)
    return template.replace("{bosses}", lines).strip()


def get_notification_preview() -> str:
    """Пример сообщения для режима просмотра настроек.

    Использует выбранных боссов, респающих сегодня; если таких нет — демо-босс,
    чтобы пример всегда был показательным.
    """
    bosses = get_bosses_for_notification()
    if not bosses:
        bosses = [_demo_boss()]
    return generate_notification_text(bosses)


def _record_log(*, notify_date: date, bosses: list[str], text: str, success: bool) -> bool:
    """Write an EpicBossNotificationLog row; swallow IntegrityError (duplicate date).

    The create is wrapped in a savepoint (transaction.atomic) so a unique
    constraint hit rolls back cleanly without breaking the enclosing transaction.
    """
    try:
        with transaction.atomic():
            EpicBossNotificationLog.objects.create(
                notify_date=notify_date,
                bosses=bosses,
                text=text,
                success=success,
            )
        return True
    except IntegrityError:
        logger.info(
            "Epic boss notification already logged for %s; skipping duplicate.",
            notify_date,
        )
        return False


def send_epic_boss_notification() -> None:
    """Send today's Epic RB notification if due.

    Exits silently when notifications are disabled, the notification time
    (MSK) has not been reached yet, already sent today, or no selected boss
    respawns today. A missing active Telegram group is logged and the failure
    is recorded in the log without raising.
    """
    settings_obj = get_settings()
    if not settings_obj.is_enabled:
        logger.info("Epic boss notifications disabled; skipping.")
        return

    now_msk = timezone.localtime().time()
    if now_msk < settings_obj.notification_time:
        logger.info(
            "Notification time %s not reached yet (now %s MSK); skipping.",
            settings_obj.notification_time,
            now_msk,
        )
        return

    today = timezone.localdate()
    if not should_notify_today(today):
        logger.info("Epic boss notification already sent today (%s); skipping.", today)
        return

    bosses = get_bosses_for_notification()
    if not bosses:
        logger.info("No selected boss respawns today (%s); skipping.", today)
        return

    text = generate_notification_text(bosses)
    boss_names = [b.boss_name for b in bosses]

    try:
        messaging_service.send_epic_boss_notification(settings_obj, text)
    except messaging_service.MessagingError as exc:
        logger.error("Failed to send epic boss notification: %s", exc)
        _record_log(
            notify_date=today, bosses=boss_names, text=text, success=False
        )
        return

    _record_log(notify_date=today, bosses=boss_names, text=text, success=True)
    logger.info("Epic boss notification sent for %s (bosses: %s)", today, boss_names)
