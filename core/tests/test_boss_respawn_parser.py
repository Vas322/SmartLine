"""Tests for the boss respawn HTML parser (craft-calc.ru fixture)."""
from datetime import datetime
from pathlib import Path

from django.test import SimpleTestCase

from core.services.boss_respawn_parser import (
    parse_bosses_from_html,
    parse_naive_dt,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "boss_respawn_page.html"


def _fixture() -> str:
    return FIXTURE.read_text(encoding="utf-8")


class ParseNaiveDtTests(SimpleTestCase):
    """Naive datetime parsing: source times are Moscow local (no tzinfo)."""

    def test_parses_naive_datetime_without_tzinfo(self):
        dt = parse_naive_dt("2026-09-29 15:59:21")
        self.assertEqual(dt, datetime(2026, 9, 29, 15, 59, 21))
        self.assertIsNone(dt.tzinfo)

    def test_preserves_exact_clock_time(self):
        # No timezone conversion happens — the string is taken as-is.
        dt = parse_naive_dt("2026-01-15 12:00:00")
        self.assertEqual(dt, datetime(2026, 1, 15, 12, 0, 0))


class ParseBossesFromHtmlTests(SimpleTestCase):
    """Parsing the x5 sections from the fixture page."""

    def test_parses_all_seven_bosses(self):
        bosses = parse_bosses_from_html(_fixture())
        self.assertEqual(len(bosses), 7)

    def test_subclass_bosses(self):
        bosses = parse_bosses_from_html(_fixture())
        subclass = [b for b in bosses if b.boss_type == "SUBCLASS"]
        self.assertEqual(len(subclass), 4)
        names = {b.boss_name for b in subclass}
        self.assertEqual(
            names,
            {
                "Shilen's Messenger Cabrio",
                "Death Lord Hallate",
                "Kernon",
                "Longhorn Golkonda",
            },
        )

    def test_epic_bosses(self):
        bosses = parse_bosses_from_html(_fixture())
        epic = [b for b in bosses if b.boss_type == "EPIC"]
        self.assertEqual(len(epic), 3)
        names = {b.boss_name for b in epic}
        self.assertEqual(names, {"Antharas", "Valakas", "Baium"})

    def test_locations_and_started(self):
        bosses = parse_bosses_from_html(_fixture())
        by_name = {b.boss_name: b for b in bosses}

        cabrio = by_name["Shilen's Messenger Cabrio"]
        self.assertEqual(cabrio.location, "The Cemetery")
        self.assertTrue(cabrio.started)  # «Респ идёт» в фикстуре

        hallate = by_name["Death Lord Hallate"]
        self.assertEqual(hallate.location, "ToI 3")
        self.assertFalse(hallate.started)

        antharas = by_name["Antharas"]
        self.assertEqual(antharas.location, "LoA")

    def test_times_parsed_as_naive_moscow(self):
        bosses = parse_bosses_from_html(_fixture())
        cabrio = next(b for b in bosses if b.boss_name == "Shilen's Messenger Cabrio")
        # Source string is taken as-is (Moscow local time, no conversion).
        self.assertEqual(cabrio.respawn_start, datetime(2026, 9, 19, 6, 44, 1))
        self.assertEqual(cabrio.respawn_end, datetime(2026, 9, 19, 18, 44, 1))
        self.assertIsNone(cabrio.respawn_start.tzinfo)
        self.assertIsNone(cabrio.respawn_end.tzinfo)

    def test_empty_html_returns_empty_list(self):
        self.assertEqual(parse_bosses_from_html(""), [])
        self.assertEqual(parse_bosses_from_html("<html></html>"), [])

    def test_no_x5_section_returns_empty_list(self):
        # Страница без x5-секций (изменилась разметка) — не падает, пусто.
        html = "<div id='x1-epic'>...</div><div id='x3-subclass'>...</div>"
        self.assertEqual(parse_bosses_from_html(html), [])
