"""Business logic for calculating scheduled message run times."""
import logging
from datetime import date, datetime, time, timedelta
from typing import Optional

from django.utils import timezone
from zoneinfo import ZoneInfo

from core.models import ScheduledMessage

logger = logging.getLogger(__name__)

# Advisory lock constant for the management command
SCHEDULER_ADVISORY_LOCK_ID = 123456789

# MSK timezone constant
MSK_TZ = ZoneInfo("Europe/Moscow")


def _aware_dt(dt: datetime) -> datetime:
    """Ensure datetime is timezone-aware in MSK."""
    if timezone.is_naive(dt):
        return dt.replace(tzinfo=MSK_TZ)
    return dt.astimezone(MSK_TZ)


def _now_msk() -> datetime:
    """Return current time in MSK timezone."""
    return timezone.now().astimezone(MSK_TZ)


def _weekday_names() -> list[str]:
    """Return Russian weekday names (Mon=0 ... Sun=6)."""
    return ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def weekdays_display(weekdays: list[int]) -> str:
    """Format weekdays list as readable string."""
    names = _weekday_names()
    return ", ".join(names[d] for d in sorted(weekdays) if 0 <= d <= 6)


def _next_weekly_dt(after: datetime, target_weekdays: list[int], run_time: time) -> Optional[datetime]:
    """Return the next datetime strictly after 'after' that matches target_weekdays at run_time."""
    if not target_weekdays:
        return None

    after = _aware_dt(after)
    after_date = after.date()

    # Check up to 8 days ahead (covers same day next week)
    for i in range(8):
        candidate_date = after_date + timedelta(days=i)
        if candidate_date.weekday() in target_weekdays:
            candidate_dt = _aware_dt(datetime.combine(candidate_date, run_time))
            if candidate_dt > after:
                return candidate_dt
    return None


def _next_biweekly_dt(after: datetime, start_date: date, target_weekdays: list[int], run_time: time) -> Optional[datetime]:
    """Return the next biweekly datetime strictly after 'after' that matches target_weekdays."""
    if not target_weekdays:
        return None

    after = _aware_dt(after)
    after_date = after.date()

    # Find the first biweekly date >= after_date
    days_diff = (after_date - start_date).days
    if days_diff <= 0:
        n = 0
    else:
        n = (days_diff + 13) // 14  # ceiling division

    # Check up to a reasonable number of periods (e.g., 2 years = 104 periods)
    for _ in range(104):
        candidate_date = start_date + timedelta(days=14 * n)
        if candidate_date.weekday() in target_weekdays:
            candidate_dt = _aware_dt(datetime.combine(candidate_date, run_time))
            if candidate_dt > after:
                return candidate_dt
        n += 1
    return None


def _next_monthly_dt(after: datetime, start_date: date, run_time: time) -> Optional[datetime]:
    """Return the next monthly datetime strictly after 'after' on the same day of month as start_date."""
    after = _aware_dt(after)
    after_date = after.date()
    target_day = start_date.day

    # Start from the month of after_date
    year = after_date.year
    month = after_date.month

    # Check current month and subsequent months
    for _ in range(24):  # Check up to 2 years
        try:
            candidate_date = date(year, month, target_day)
        except ValueError:
            # Day doesn't exist in this month (e.g., Feb 31), use last day
            if month == 12:
                candidate_date = date(year + 1, 1, 1) - timedelta(days=1)
            else:
                candidate_date = date(year, month + 1, 1) - timedelta(days=1)

        candidate_dt = _aware_dt(datetime.combine(candidate_date, run_time))
        if candidate_dt > after:
            return candidate_dt

        # Move to next month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return None


def _next_custom_dt(after: datetime, custom_dates: list[str], run_time: time) -> Optional[datetime]:
    """Return the next datetime from custom_dates strictly after 'after'."""
    if not custom_dates:
        return None

    after = _aware_dt(after)
    after_date = after.date()

    # Parse and sort custom dates
    parsed_dates = []
    for d_str in custom_dates:
        try:
            parsed_dates.append(datetime.strptime(d_str, "%Y-%m-%d").date())
        except ValueError:
            logger.warning("Invalid custom date format: %s", d_str)
            continue

    parsed_dates.sort()
    for d in parsed_dates:
        candidate_dt = _aware_dt(datetime.combine(d, run_time))
        if candidate_dt > after:
            return candidate_dt
    return None


def next_run(schedule: ScheduledMessage, after: Optional[datetime] = None) -> Optional[datetime]:
    """Calculate the next run time for a schedule after the given datetime.

    Args:
        schedule: The ScheduledMessage instance.
        after: The datetime to calculate from (aware, MSK). Defaults to now.

    Returns:
        Aware datetime in MSK of the next run, or None if schedule has ended.
    """
    if not schedule.is_active:
        return None

    if after is None:
        after = _now_msk()

    after = _aware_dt(after)

    # Check end_date
    if schedule.end_date and after.date() > schedule.end_date:
        return None

    run_time = schedule.time

    next_dt: Optional[datetime] = None

    if schedule.frequency == ScheduledMessage.Frequency.WEEKLY:
        next_dt = _next_weekly_dt(after, schedule.weekdays, run_time)

    elif schedule.frequency == ScheduledMessage.Frequency.BIWEEKLY:
        next_dt = _next_biweekly_dt(after, schedule.start_date, schedule.weekdays, run_time)

    elif schedule.frequency == ScheduledMessage.Frequency.MONTHLY:
        next_dt = _next_monthly_dt(after, schedule.start_date, run_time)

    elif schedule.frequency == ScheduledMessage.Frequency.CUSTOM_DATES:
        next_dt = _next_custom_dt(after, schedule.custom_dates, run_time)

    if next_dt is None:
        return None

    # Check end_date for the found datetime
    if schedule.end_date and next_dt.date() > schedule.end_date:
        return None

    return next_dt


def computed_next_run(schedule: ScheduledMessage) -> Optional[datetime]:
    """Compute next run for display in admin, considering last_sent_at and current time."""
    after = schedule.last_sent_at if schedule.last_sent_at else _now_msk()
    return next_run(schedule, after=after)


def due_schedules(now: Optional[datetime] = None) -> list[ScheduledMessage]:
    """Return all active schedules that are due to run at the given time (within the current minute).

    A schedule is due if:
    - is_active=True
    - The next scheduled run time (after last_sent_at, or from start_date if never sent) is within the current minute window
    - last_sent_at is not in the same minute as the computed next_run (prevents duplicates)
    """
    if now is None:
        now = _now_msk()

    now = _aware_dt(now)
    # Truncate to minute precision for comparison
    now_minute = now.replace(second=0, microsecond=0)
    # Window: 5 minutes back (scheduler runs every 5 minutes)
    window_start = now_minute - timedelta(minutes=5)

    due = []
    for schedule in ScheduledMessage.objects.filter(is_active=True).select_related("topic"):
        # Calculate the next run time that should have occurred by now
        # If never sent, check from start_date at 00:00; otherwise check from last_sent_at
        if schedule.last_sent_at:
            after = _aware_dt(schedule.last_sent_at)
        else:
            # Start checking from the beginning of start_date
            after = _aware_dt(datetime.combine(schedule.start_date, time(0, 0)))

        next_dt = next_run(schedule, after=after)

        if next_dt is None:
            continue

        # Truncate next_dt to minute precision
        next_minute = next_dt.replace(second=0, microsecond=0)

        # Check if due (next_minute within the current 5-minute window)
        if window_start <= next_minute <= now_minute:
            # Prevent duplicate in same minute
            if schedule.last_sent_at:
                last_minute = _aware_dt(schedule.last_sent_at).replace(second=0, microsecond=0)
                if last_minute == next_minute:
                    continue
            due.append(schedule)

    return due


def try_acquire_lock() -> bool:
    """Try to acquire the PostgreSQL advisory lock for the scheduler.

    On PostgreSQL the lock prevents a second scheduler instance from running
    concurrently. On non-PostgreSQL vendors (e.g. SQLite in local dev) advisory
    locks are unavailable, so the lock is treated as always free.

    Returns True if the lock is acquired (or the vendor has no advisory locks),
    False if another process holds it.
    """
    from django.db import connection

    if connection.vendor != "postgresql":
        return True

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [SCHEDULER_ADVISORY_LOCK_ID])
        result = cursor.fetchone()
        return bool(result[0]) if result else False


def release_lock() -> None:
    """Release the PostgreSQL advisory lock.

    On non-PostgreSQL vendors (e.g. SQLite in local dev) there is nothing to
    release, so this is a no-op.
    """
    from django.db import connection

    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", [SCHEDULER_ADVISORY_LOCK_ID])


def run_due_schedules() -> None:
    """Send all schedules that are currently due.

    Intended for the in-process scheduler thread (dev command): it iterates
    due_schedules() and sends each one, logging and swallowing per-schedule
    errors so one failure does not stop the rest. No advisory lock is taken —
    in dev everything runs in a single process.
    """
    from core.services.messaging_service import MessagingError, send_scheduled_message

    for schedule in due_schedules():
        try:
            send_scheduled_message(schedule)
            logger.info(
                "Scheduled message sent (in-process) schedule_id=%s '%s'",
                schedule.pk,
                schedule.name,
            )
        except MessagingError as exc:
            logger.error(
                "Failed to send scheduled message (in-process) schedule_id=%s: %s",
                schedule.pk,
                exc,
            )
        except Exception:
            logger.exception(
                "Unexpected error sending scheduled message (in-process) schedule_id=%s",
                schedule.pk,
            )