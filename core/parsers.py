"""Deterministic parser for Smartline activity Telegram messages.

The parser is a pure function: no ORM, no Telegram API. It converts a raw
message string into a :class:`ParsedActivity` or raises :class:`ParserError`.
"""
import re
from dataclasses import dataclass
from datetime import time
from decimal import Decimal, InvalidOperation

_DEF_TOKENS = {"def", "деф"}
_FARM_TOKENS = {"farm", "фарм"}
_CAST_TOKENS = {"cast", "каст", "recast", "перекаст"}
_RECOGNIZED_TOKENS = _DEF_TOKENS | _FARM_TOKENS | _CAST_TOKENS

_TOKEN_CATEGORY = {
    "def": "DEF",
    "деф": "DEF",
    "farm": "FARM",
    "фарм": "FARM",
    "cast": "CAST",
    "каст": "CAST",
    "recast": "CAST",
    "перекаст": "CAST",
}

_SEP_RE = re.compile(r'(?:\||-|–|—)')
_TYPE_TOKEN_RE = re.compile(r'[+\s]+')
_WAVE_TIME_RE = re.compile(r'^(\d{1,2})[.:](\d{2})$')
_TIME_WITH_REST_RE = re.compile(r'^(\d{1,2})[.:](\d{2})(?:[.,;]?\s*(.*))?$')

# Registration parser
_REG_KEYWORDS = {"рега", "регистрация"}
_CLANS_RE = re.compile(r'^(\d+)\s*(.*)$', re.IGNORECASE)
_CLANT_WORDS_RE = re.compile(r'^(?:кланами|кланов|клан|клана)\b\s*(.*)$', re.IGNORECASE)


class ParserError(ValueError):
    """Raised when an activity message cannot be parsed."""


@dataclass
class ParsedActivity:
    amount: Decimal
    activity_type: str  # 'DEF' | 'FARM' | 'CAST'
    has_cast: bool
    nickname: str
    wave_start: time
    description: str


@dataclass
class ParsedRegistration:
    clans_count: int
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


def _split_type_tokens(raw: str) -> list[str]:
    """Split a TYPE field into lowercased tokens.

    Tokens may be separated by "+" and/or whitespace: "деф+каст",
    "деф  +  каст", "деф каст" are equivalent.
    """
    return [token for token in _TYPE_TOKEN_RE.split(raw.strip().lower()) if token]


def _part_has_known_type(part: str) -> bool:
    """Return True when any token in a field is a recognized type word."""
    return any(token in _RECOGNIZED_TOKENS for token in _split_type_tokens(part))


def _parse_activity_type(raw: str) -> tuple[str, bool]:
    """Parse a (possibly compound) TYPE field.

    Returns ``(activity_type, has_cast)``. Raises :class:`ParserError` for
    unknown tokens, DEF+FARM conflicts and duplicate tokens of the same
    category.
    """
    tokens = _split_type_tokens(raw)
    categories = []
    for token in tokens:
        category = _TOKEN_CATEGORY.get(token)
        if category is None:
            raise ParserError("unknown_activity_type")
        categories.append(category)

    if "DEF" in categories and "FARM" in categories:
        raise ParserError("def_and_farm_conflict")

    if len(set(categories)) != len(categories):
        raise ParserError("duplicate_type")

    if "CAST" in categories:
        if "DEF" in categories:
            return "DEF", True
        if "FARM" in categories:
            return "FARM", True
        return "CAST", True
    if "DEF" in categories:
        return "DEF", False
    if "FARM" in categories:
        return "FARM", False
    raise ParserError("unknown_activity_type")


def _parse_wave_time(raw: str) -> time:
    match = _WAVE_TIME_RE.match(raw)
    if match is None:
        raise ParserError("invalid_wave_time")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ParserError("invalid_wave_time")
    return time(hour=hour, minute=minute)


def _parse_wave_time_flexible(raw: str):
    raw = raw.strip()
    try:
        return _parse_wave_time(raw), ""
    except ParserError:
        pass
    match = _TIME_WITH_REST_RE.match(raw)
    if match is None:
        raise ParserError("invalid_wave_time")
    hour = int(match.group(1))
    minute = int(match.group(2))
    if hour > 23 or minute > 59:
        raise ParserError("invalid_wave_time")
    rest = (match.group(3) or "").strip()
    return time(hour=hour, minute=minute), rest


def parse_activity_message(text: str) -> ParsedActivity:
    """Parse a Telegram activity message into structured data.

    Expected format: ``+X | TYPE | NICK | TIME | DESCRIPTION``. Field order is
    strict: amount, then type, then nickname, then wave start time, then
    description. DESCRIPTION may be omitted; any additional ``|`` symbols
    inside DESCRIPTION are preserved.
    """
    stripped = text.strip()
    if not stripped.startswith("+"):
        raise ParserError("message_does_not_start_with_plus")

    rest = stripped[1:]
    parts = [part.strip() for part in _SEP_RE.split(rest, maxsplit=4)]
    if len(parts) == 1:
        # No field separators (| - – —) were used; the whole message is a
        # single blob, so the generic "missing wave time" error would be
        # misleading.
        raise ParserError("missing_field_separators")
    if len(parts) < 4:
        # Message has separators but fewer than the 4 structural fields
        # (amount, type, nick, time). Instead of always blaming the wave
        # time, inspect the available parts to name the actually missing
        # role (type / time / nickname).
        remaining = parts[1:]
        has_type = any(_part_has_known_type(p) for p in remaining)
        has_time = any(_TIME_WITH_REST_RE.match(p) for p in remaining)
        if _part_has_known_type(parts[1]):
            # The type slot is filled with a compound type; validate it
            # fully so conflict/duplicate/unknown errors surface instead of
            # a generic missing-field message.
            _parse_activity_type(parts[1])
        elif (
            not has_time
            and parts[1].strip()
            and not _TIME_WITH_REST_RE.match(parts[1])
        ):
            # The type slot is filled with an unrecognized word and there is
            # no plausible time field, e.g. "+1 | блабла | Swettka".
            raise ParserError("unknown_activity_type")
        if not has_type:
            raise ParserError("missing_activity_type")
        if not has_time:
            raise ParserError("missing_wave_time")
        # Type and time are present but there is no room for the nickname.
        raise ParserError("empty_nickname")

    amount_part, type_part, nickname = parts[0], parts[1], parts[2]
    time_part = parts[3]
    amount = _parse_amount(amount_part)
    activity_type, has_cast = _parse_activity_type(type_part)
    wave_start, time_extra = _parse_wave_time_flexible(time_part)

    if len(parts) > 4:
        description = (time_extra + " " + parts[4]).strip()
    else:
        description = time_extra

    if not nickname:
        raise ParserError("empty_nickname")

    if not re.fullmatch(r"[A-Za-zА-Яа-яЁё0-9]+", nickname):
        raise ParserError("invalid_nickname")

    return ParsedActivity(
        amount=amount,
        activity_type=activity_type,
        has_cast=has_cast,
        nickname=nickname,
        wave_start=wave_start,
        description=description,
    )


def parse_registration_message(text: str) -> ParsedRegistration:
    """Parse a Telegram registration message into structured data.

    Expected format: ``рега N кланов описание`` or ``регистрация N кланов описание``.
    The keyword (рега/регистрация) must be at the start (case-insensitive, word boundary).
    Then an integer number of clans is required, optionally followed by "кланами/кланов/клан".
    The rest is description (may be empty).
    """
    stripped = text.strip()
    if not stripped:
        raise ParserError("registration_empty")

    lowered = stripped.lower()

    # Check for keyword at start (word boundary)
    keyword = None
    for kw in _REG_KEYWORDS:
        if lowered.startswith(kw):
            # Ensure word boundary: next char is space or end of string
            if len(stripped) == len(kw) or stripped[len(kw)].isspace():
                keyword = kw
                break

    if keyword is None:
        raise ParserError("registration_missing_keyword")

    # Extract the rest after keyword
    rest = stripped[len(keyword):].strip()
    if not rest:
        raise ParserError("registration_missing_clans_count")

    # Parse clans count and description
    match = _CLANS_RE.match(rest)
    if not match:
        raise ParserError("registration_invalid_clans_count")

    clans_count_str, description = match.groups()
    try:
        clans_count = int(clans_count_str)
    except ValueError:
        raise ParserError("registration_invalid_clans_count")

    if clans_count <= 0:
        raise ParserError("registration_invalid_clans_count")

    # Strip optional "кланами/кланов/клан" word from description
    clan_word_match = _CLANT_WORDS_RE.match(description)
    if clan_word_match:
        description = clan_word_match.group(1)

    return ParsedRegistration(
        clans_count=clans_count,
        description=description.strip(),
    )
