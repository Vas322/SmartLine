"""Tests for the boss respawn HTML parser (craft-calc.ru fixture)."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from core.services.boss_respawn_parser import (
    convert_est_to_utc,
    parse_bosses_from_html,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "boss_respawn_page.html"

UTC = ZoneInfo("UTC")


def _fixture() -> str:
    return FIXTURE.read_text(encoding="utf-8")


class ConvertEstToUtcTests(SimpleTestCase):
    """Timezone conversion: EST (winter, UTC-5) and EDT (summer, UTC-4)."""

    def test_winter_est_is_utc_minus_5(self):
        # Январь — EST (UTC-5).
        dt = convert_est_to_utc("2026-01-15 12:00:00", "EST")
        expected = datetime(2026, 1, 15, 17, 0, 0, tzinfo=UTC)
        self.assertEqual(dt, expected)

    def test_summer_edt_is_utc_minus_4(self):
        # Июль — EDT (UTC-4).
        dt = convert_est_to_utc("2026-07-15 12:00:00", "EST")
        expected = datetime(2026, 7, 15, 16, 0, 0, tzinfo=UTC)
        self.assertEqual(dt, expected)

    def test_dst_transition_uses_correct_offset(self):
        # Вторая неделя марта 2026 — переход на EDT (UTC-4).
        dt = convert_est_to_utc("2026-03-15 12:00:00", "EST")
        expected = datetime(2026, 3, 15, 16, 0, 0, tzinfo=UTC)
        self.assertEqual(dt, expected)

    def test_unknown_timezone_raises(self):
        with self.assertRaises(ValueError):
            convert_est_to_utc("2026-01-15 12:00:00", "PST")


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

    def test_times_converted_to_utc(self):
        bosses = parse_bosses_from_html(_fixture())
        cabrio = next(b for b in bosses if b.boss_name == "Shilen's Messenger Cabrio")
        # 2026-09-19 06:44:01 EDT (UTC-4) -> 10:44:01 UTC.
        self.assertEqual(cabrio.respawn_start, datetime(2026, 9, 19, 10, 44, 1, tzinfo=UTC))
        self.assertEqual(cabrio.respawn_end, datetime(2026, 9, 19, 22, 44, 1, tzinfo=UTC))

    def test_empty_html_returns_empty_list(self):
        self.assertEqual(parse_bosses_from_html(""), [])
        self.assertEqual(parse_bosses_from_html("<html></html>"), [])

    def test_no_x5_section_returns_empty_list(self):
        # Страница без x5-секций (изменилась разметка) — не падает, пусто.
        html = "<div id='x1-epic'>...</div><div id='x3-subclass'>...</div>"
        self.assertEqual(parse_bosses_from_html(html), [])
