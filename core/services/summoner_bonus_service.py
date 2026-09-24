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
