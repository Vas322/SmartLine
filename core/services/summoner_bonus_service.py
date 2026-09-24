"""Business logic for the global summoner bonus settings.

This stage only provides access to the singleton SummonerBonusSettings
(pk=1); the bonus calculation itself is out of scope.
"""
import logging

from core.models import SummonerBonusSettings

logger = logging.getLogger(__name__)


def get_settings() -> SummonerBonusSettings:
    """Return the singleton SummonerBonusSettings (pk=1)."""
    settings_obj, _ = SummonerBonusSettings.objects.get_or_create(pk=1)
    return settings_obj
