"""Excel export of activities for a period."""
import io
from datetime import datetime
from decimal import Decimal

from openpyxl import Workbook

from core.models import Activity


def _paid_amount(activity: Activity) -> Decimal:
    if activity.activity_type == Activity.ActivityType.DEF:
        return activity.amount
    if activity.has_cast:
        return activity.amount
    return Decimal("0")


def _display_amount(amount: Decimal) -> str:
    """Represent a Decimal for Excel display without trailing zeros."""
    return str(amount.normalize())


def export_activities_excel(date_from: datetime, date_to: datetime) -> io.BytesIO:
    """Build an XLSX workbook with activities in the date range.

    PostgreSQL is the source of truth; Excel is only an export format.
    """
    activities = (
        Activity.objects.filter(created_at__range=(date_from, date_to))
        .select_related("player", "telegram_message")
        .order_by("created_at")
    )

    headers = [
        "Дата",
        "Игрок",
        "Тип",
        "Количество часов",
        "Минуты",
        "Оплачиваемые часы",
        "Описание",
        "Исходное сообщение",
        "Telegram message id",
    ]

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Activities"
    sheet.append(headers)

    for activity in activities:
        minutes = int(activity.amount * 60)
        sheet.append(
            [
                activity.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                activity.player.nickname,
                activity.type_display,
                _display_amount(activity.amount),
                minutes,
                _display_amount(_paid_amount(activity)),
                activity.description,
                activity.telegram_message.text,
                activity.telegram_message.telegram_message_id,
            ]
        )

    stream = io.BytesIO()
    workbook.save(stream)
    stream.seek(0)
    return stream