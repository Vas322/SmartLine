"""Tests for the public boss respawn page (/rb/)."""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import BossRespawn, BossRespawnSyncStatus


class BossRespawnPageTests(TestCase):
    """Public /rb/ page — no authentication required."""

    def setUp(self):
        self.epic = BossRespawn.objects.create(
            boss_name="Antharas",
            boss_type=BossRespawn.BossType.EPIC,
            respawn_start=timezone.now(),
            respawn_end=timezone.now() + timedelta(hours=1),
            location="LoA",
        )
        self.sub = BossRespawn.objects.create(
            boss_name="Kernon",
            boss_type=BossRespawn.BossType.SUBCLASS,
            respawn_start=timezone.now(),
            respawn_end=timezone.now() + timedelta(hours=1),
            location="ToI 8",
        )

    def test_anonymous_can_access_page(self):
        response = self.client.get(reverse("boss_respawn"))
        self.assertEqual(response.status_code, 200)

    def test_page_has_title(self):
        response = self.client.get(reverse("boss_respawn"))
        self.assertContains(response, "Респ РБ — Asterios x5")

    def test_header_link_present_for_anonymous(self):
        response = self.client.get(reverse("boss_respawn"))
        self.assertContains(response, "Респ РБ")

    def test_default_filter_shows_all(self):
        response = self.client.get(reverse("boss_respawn"))
        self.assertContains(response, "Antharas")
        self.assertContains(response, "Kernon")

    def test_invalid_filter_defaults_to_all(self):
        response = self.client.get(reverse("boss_respawn"), {"filter": "bogus"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Antharas")
        self.assertContains(response, "Kernon")

    def test_filter_epic(self):
        response = self.client.get(reverse("boss_respawn"), {"filter": "epic"})
        self.assertContains(response, "Antharas")
        self.assertNotContains(response, "Kernon")

    def test_filter_subclass(self):
        response = self.client.get(reverse("boss_respawn"), {"filter": "subclass"})
        self.assertContains(response, "Kernon")
        self.assertNotContains(response, "Antharas")

    def test_empty_db_shows_unavailable(self):
        BossRespawn.objects.all().delete()
        response = self.client.get(reverse("boss_respawn"))
        self.assertContains(response, "Расписание временно недоступно")

    def test_stale_data_warning(self):
        BossRespawnSyncStatus.objects.create(
            pk=1,
            last_success_at=timezone.now() - timedelta(hours=3),
        )
        response = self.client.get(reverse("boss_respawn"))
        self.assertContains(response, "Данные могут быть устаревшими")

    def test_fresh_data_no_warning(self):
        BossRespawnSyncStatus.objects.create(
            pk=1,
            last_success_at=timezone.now(),
        )
        response = self.client.get(reverse("boss_respawn"))
        self.assertNotContains(response, "Данные могут быть устаревшими")
