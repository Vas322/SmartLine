"""Tests for the boss respawn service (sync, upsert, queries)."""
from datetime import timedelta
from pathlib import Path
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from core.models import BossRespawn, BossRespawnSyncStatus
from core.services import boss_respawn_service

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "boss_respawn_page.html"


def _fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


class FetchAndSyncTests(TestCase):
    """fetch_and_sync: fetch -> parse -> upsert -> sync status."""

    def test_success_stores_bosses_and_updates_status(self):
        with mock.patch.object(boss_respawn_service, "_fetch_html", return_value=_fixture_html()):
            ok = boss_respawn_service.fetch_and_sync()

        self.assertTrue(ok)
        self.assertEqual(BossRespawn.objects.count(), 7)

        status = boss_respawn_service.get_sync_status()
        self.assertIsNotNone(status.last_success_at)
        self.assertEqual(status.last_error, "")
        self.assertIsNone(status.last_error_at)

        # Данные сохранились корректно.
        antharas = BossRespawn.objects.get(boss_name="Antharas")
        self.assertEqual(antharas.boss_type, BossRespawn.BossType.EPIC)
        self.assertEqual(antharas.location, "LoA")
        self.assertTrue(antharas.is_parsed_successfully)

    def test_dedup_on_second_sync(self):
        with mock.patch.object(boss_respawn_service, "_fetch_html", return_value=_fixture_html()):
            boss_respawn_service.fetch_and_sync()
            boss_respawn_service.fetch_and_sync()

        # Уникальность по boss_name — повторная синхронизация не плодит дубли.
        self.assertEqual(BossRespawn.objects.count(), 7)
        self.assertEqual(
            BossRespawn.objects.filter(boss_name="Antharas").count(),
            1,
        )

    def test_network_error_sets_last_error_and_keeps_data(self):
        # Существующие данные остаются на странице при ошибке.
        with mock.patch.object(boss_respawn_service, "_fetch_html", return_value=_fixture_html()):
            boss_respawn_service.fetch_and_sync()

        with mock.patch.object(
            boss_respawn_service,
            "_fetch_html",
            side_effect=RuntimeError("connection refused"),
        ):
            ok = boss_respawn_service.fetch_and_sync()

        self.assertFalse(ok)
        status = boss_respawn_service.get_sync_status()
        self.assertIsNotNone(status.last_error_at)
        self.assertIn("connection refused", status.last_error)
        # Старые данные целы.
        self.assertEqual(BossRespawn.objects.count(), 7)

    def test_markup_changed_no_cards_sets_error(self):
        with mock.patch.object(
            boss_respawn_service,
            "parse_bosses_from_html",
            return_value=[],
        ):
            ok = boss_respawn_service.fetch_and_sync()

        self.assertFalse(ok)
        status = boss_respawn_service.get_sync_status()
        self.assertIn("No boss cards parsed", status.last_error)

    def test_last_attempt_at_is_set(self):
        with mock.patch.object(boss_respawn_service, "_fetch_html", return_value=_fixture_html()):
            boss_respawn_service.fetch_and_sync()
        status = boss_respawn_service.get_sync_status()
        self.assertIsNotNone(status.last_attempt_at)


class QueryTests(TestCase):
    """get_all_bosses / get_sync_status."""

    def test_get_all_bosses_ordered_by_respawn_start(self):
        BossRespawn.objects.create(
            boss_name="B", boss_type="EPIC",
            respawn_start=timezone.now() + timedelta(days=2),
            respawn_end=timezone.now() + timedelta(days=3),
        )
        BossRespawn.objects.create(
            boss_name="A", boss_type="SUBCLASS",
            respawn_start=timezone.now(),
            respawn_end=timezone.now() + timedelta(hours=1),
        )
        bosses = boss_respawn_service.get_all_bosses()
        self.assertEqual([b.boss_name for b in bosses], ["A", "B"])

    def test_get_sync_status_creates_singleton(self):
        s1 = boss_respawn_service.get_sync_status()
        s2 = boss_respawn_service.get_sync_status()
        self.assertEqual(s1.pk, 1)
        self.assertEqual(s2.pk, 1)
        self.assertEqual(BossRespawnSyncStatus.objects.count(), 1)
