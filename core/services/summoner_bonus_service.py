"""Business logic for the global summoner bonus settings.

This stage provides access to the singleton SummonerBonusSettings
(pk=1) and the bonus calculation itself.
"""
import logging
from decimal import ROUND_HALF_UP, Decimal

from core.models import SummonerBonusSettings

logger = logging.getLogger(__name__)


def get_settings() -> SummonerBonusSettings:
    """Return the singleton SummonerBonusSettings (pk=1)."""
    settings_obj, _ = SummonerBonusSettings.objects.get_or_create(pk=1)
    return settings_obj


def calculate_bonus(def_payment: Decimal, summoner_count: int, percent: Decimal) -> Decimal:
    if summoner_count <= 0 or percent <= 0 or def_payment <= 0:
        return Decimal("0.00")
    bonus = def_payment * summoner_count * percent / Decimal("100")
    return bonus.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def stamp_bonus(activity) -> Decimal:
    """Бонус по активности НА МОМЕНТ СОЗДАНИЯ (не пересчитывается потом)."""
    settings_obj = get_settings()
    if not settings_obj.is_enabled or activity.activity_type != "DEF":
        return Decimal("0.00")
    if settings_obj.enabled_at and activity.created_at < settings_obj.enabled_at:
        return Decimal("0.00")
    return calculate_bonus(
        activity.payment_kk or Decimal("0"),
        activity.player.summoner_count or 0,
        settings_obj.percent,
    )
