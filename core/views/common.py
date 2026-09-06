"""Common imports and helpers for the views package."""
import logging
from decimal import Decimal



logger = logging.getLogger(__name__)

MEMBERS_GROUP = "Members"


def _percent(total_hours: Decimal, days_in_period: int) -> Decimal:
    """Attendance percent with a hard cap of 100, rounded to 2 places."""
    denominator = Decimal(days_in_period * 5)
    if denominator <= 0:
        return Decimal("0")
    percent = (total_hours / denominator) * Decimal("100")
    if percent > Decimal("100"):
        percent = Decimal("100")
    return percent.quantize(Decimal("0.01"))
