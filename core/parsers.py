"""Deterministic parser for Smartline activity Telegram messages.

The parser is a pure function: no ORM, no Telegram API. It converts a raw
message string into a :class:`ParsedActivity` or raises :class:`ParserError`.
"""
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import List

_ACTIVITY_TYPE_MAP = {
    "деф": "DEF",
    "def": "DEF",
    "фарм": "FARM",
    "farm": "FARM",
}

_SEP_RE = re.compile(r'(?:\||-|–|—)')


class ParserError(ValueError):
    """Raised when an activity message cannot be parsed."""


@dataclass
class ParsedActivity:
    amount: Decimal
    activity_type: str  # 'DEF' | 'FARM'
    nicknames: List[str]
    description: str


def _parse_amount(raw: str) -> Decimal:
    cleaned = raw.strip().replace(",", ".")
    if not cleaned:
        raise ParserError("invalid_amount")
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ParserError("invalid_amount") from exc
    if amount <= 0:
        raise ParserError("invalid_amount")
    return amount


def _normalize_activity_type(raw: str) -> str:
    key = raw.strip().lower()
    activity_type = _ACTIVITY_TYPE_MAP.get(key)
    if activity_type is None:
        raise ParserError("invalid_activity_type")
    return activity_type


def parse_activity_message(text: str) -> ParsedActivity:
    """Parse a Telegram activity message into structured data.

    Expected format: ``+X | TYPE | NICK | DESCRIPTION``. Additional ``|``
    symbols inside DESCRIPTION are preserved.
    """
    stripped = text.strip()
    if not stripped.startswith("+"):
        raise ParserError("message_does_not_start_with_plus")

    rest = stripped[1:]
    parts = [part.strip() for part in _SEP_RE.split(rest, maxsplit=3)]
    if len(parts) < 3:
        raise ParserError("invalid_format")

    amount_part, type_part, nickname = parts[0], parts[1], parts[2]
    description = parts[3] if len(parts) > 3 else ""
    amount = _parse_amount(amount_part)
    activity_type = _normalize_activity_type(type_part)

    if not nickname:
        raise ParserError("empty_nickname")

    nick_parts = [n.strip() for n in nickname.split(",")]
    nicknames: list[str] = []
    seen = set()
    for n in nick_parts:
        if not n:
            continue
        key = n.lower()
        if key in seen:
            continue  # тихий дедуп case-insensitive
        seen.add(key)
        nicknames.append(n)
    if not nicknames:
        raise ParserError("empty_nickname")

    return ParsedActivity(
        amount=amount,
        activity_type=activity_type,
        nicknames=nicknames,
        description=description,
    )
