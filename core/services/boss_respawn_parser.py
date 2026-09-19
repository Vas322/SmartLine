"""Deterministic parser for the craft-calc.ru boss respawn page.

Parses the x5 server sections (ids `x5-epic` and `x5-subclass`) using only the
stdlib `html.parser`. Times on the source page are in North-American Eastern
time (data-timezone="EST"): EST is UTC-5 in winter and EDT is UTC-4 in summer.
Conversion to UTC is done through the `America/New_York` IANA zone so both
daylight regimes are handled automatically based on the date.
"""
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

UTC = ZoneInfo("UTC")
NEW_YORK = ZoneInfo("America/New_York")

DATETIME_RE = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")

# Section ids on the page that we care about (x5 server).
EPIC_SECTION_ID = "x5-epic"
SUBCLASS_SECTION_ID = "x5-subclass"


class ParseError(Exception):
    """Raised when a boss card cannot be parsed into a BossData."""


@dataclass(frozen=True)
class BossData:
    """A single parsed boss respawn entry (times are UTC-aware)."""

    boss_name: str
    boss_type: str  # BossRespawn.BossType: "EPIC" or "SUBCLASS"
    respawn_start: datetime
    respawn_end: datetime
    location: str
    started: bool
    timezone_attr: str


def convert_est_to_utc(dt_str: str, tz_attr: str) -> datetime:
    """Parse an EST/EDT datetime string and convert it to UTC (aware).

    tz_attr is the page's data-timezone value. Only "EST" is supported (it is
    mapped to America/New_York, which resolves both EST and EDT by date).
    """
    if tz_attr != "EST":
        raise ValueError(f"Unsupported timezone attribute: {tz_attr!r}")
    naive = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
    aware = naive.replace(tzinfo=NEW_YORK)
    return aware.astimezone(UTC)


def _attr_dict(attrs: list) -> dict:
    return {k: (v or "") for k, v in attrs}


class _BossRespawnHTMLParser(HTMLParser):
    """HTMLParser that extracts boss cards from the x5 sections."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.bosses: list[dict] = []
        # Current section type ("EPIC" / "SUBCLASS") or None.
        self._section_type: str | None = None
        self._section_divs = 0
        # Current card being built, or None.
        self._card: dict | None = None
        self._card_divs = 0
        # Text capture state.
        self._in_h2 = False
        self._h2_text: list[str] = []
        self._in_p = False
        self._p_text: list[str] = []
        self._timezone: str | None = None

    # -- helpers ---------------------------------------------------------
    def _start_card(self) -> None:
        self._card = {
            "name": "",
            "paragraphs": [],  # list of (class, text)
            "timezone": None,
        }
        self._card_divs = 1
        self._timezone = None

    def _finalize_card(self) -> None:
        card = self._card
        self._card = None
        self._card_divs = 0
        if card is None:
            return
        card["timezone"] = card["timezone"] or "EST"
        try:
            self.bosses.append(_build_boss(card, self._section_type))
        except (ParseError, ValueError) as exc:
            logger.warning(
                "Skipping unparseable boss card in section %s: %s",
                self._section_type,
                exc,
            )

    # -- HTMLParser callbacks --------------------------------------------
    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "div":
            a = _attr_dict(attrs)
            div_id = a.get("id", "")
            classes = a.get("class", "")
            if div_id == EPIC_SECTION_ID:
                self._section_type = "EPIC"
                self._section_divs = 1
                return
            if div_id == SUBCLASS_SECTION_ID:
                self._section_type = "SUBCLASS"
                self._section_divs = 1
                return
            if self._section_type is None:
                return
            if self._card is not None:
                # Nested div inside a card (e.g. the countdown).
                if "nk-countdown" in classes and "data-timezone" in a:
                    self._timezone = a["data-timezone"]
                self._card_divs += 1
            elif "nk-box-line" in classes:
                self._start_card()
            else:
                self._section_divs += 1
            return
        if self._card is None:
            return
        if tag == "h2":
            self._in_h2 = True
            self._h2_text = []
        elif tag == "p":
            self._in_p = True
            self._p_text = []
            self._p_class = _attr_dict(attrs).get("class", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "h2" and self._in_h2:
            self._in_h2 = False
            if self._card is not None and not self._card["name"]:
                self._card["name"] = "".join(self._h2_text).strip()
        elif tag == "p" and self._in_p:
            self._in_p = False
            text = "".join(self._p_text).strip()
            if self._card is not None:
                self._card["paragraphs"].append((self._p_class, text))
        elif tag == "div" and self._section_type is not None:
            if self._card is not None:
                self._card_divs -= 1
                if self._card_divs <= 0:
                    self._finalize_card()
            else:
                self._section_divs -= 1
                if self._section_divs <= 0:
                    self._section_type = None

    def handle_data(self, data: str) -> None:
        if self._in_h2:
            self._h2_text.append(data)
        elif self._in_p:
            self._p_text.append(data)


def _build_boss(card: dict, section_type: str) -> BossData:
    """Turn a collected card dict into a BossData."""
    name = (card.get("name") or "").strip()
    if not name:
        raise ParseError("boss name missing")

    start_dt = end_dt = None
    location = ""
    status = None
    for p_class, text in card["paragraphs"]:
        if "Начало респа" in text:
            start_dt = text
        elif "Конец респа" in text:
            end_dt = text
        elif text in ("Респ идёт", "Респ не начался"):
            status = text
        elif "До начала" in text or "До макс" in text or "target" in p_class:
            continue
        elif not location:
            location = text

    start_match = DATETIME_RE.search(start_dt or "")
    end_match = DATETIME_RE.search(end_dt or "")
    if start_match is None or end_match is None:
        raise ParseError("respawn start/end times missing")

    tz = card.get("timezone") or "EST"
    respawn_start = convert_est_to_utc(start_match.group(0), tz)
    respawn_end = convert_est_to_utc(end_match.group(0), tz)
    started = status == "Респ идёт"
    boss_type = "EPIC" if section_type == "EPIC" else "SUBCLASS"

    return BossData(
        boss_name=name,
        boss_type=boss_type,
        respawn_start=respawn_start,
        respawn_end=respawn_end,
        location=location,
        started=started,
        timezone_attr=tz,
    )


def parse_bosses_from_html(html: str) -> list[BossData]:
    """Parse the x5 boss respawn sections of the page HTML.

    Deterministic; on a malformed/unknown card the card is logged and skipped,
    the function never raises for markup changes.
    """
    parser = _BossRespawnHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.bosses
