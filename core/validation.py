"""Validation helpers for activity messages."""
from core.models import Player
from core.parsers import ParsedActivity

VALID_ACTIVITY_TYPES = ("DEF", "FARM", "CAST")


def validate_parsed(parsed: ParsedActivity) -> None:
    """Perform basic checks on a parsed activity."""
    if parsed.amount <= 0:
        raise ValueError("amount_must_be_positive")
    if parsed.activity_type not in VALID_ACTIVITY_TYPES:
        raise ValueError("invalid_activity_type")
