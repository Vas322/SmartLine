"""Tests for the /settings/rates/ page (stage 2a, variant B)."""
from datetime import time
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from core.models import Rate


class RatesPageWebTests(TestCase):
    """Settings rates page: 4 tabs, CRUD, and backward-compat redirects."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username="kl", password="test-password-123", is_staff=True
        )
        self.client.login(username="kl", password="test-password-123")

    def _get(self, url):
        return self.client.get(url).content.decode()

    def test_rates_page_returns_200_with_four_tabs(self):
        response = self.client.get(reverse("rates"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Тарифы и надбавки", content)
        for tab in ("def", "cast", "reg", "summoner"):
            self.assertIn(f'data-tab="{tab}"', content)
            self.assertIn(f'data-panel="{tab}"', content)

    def test_def_tab_active_by_default(self):
        content = self._get(reverse("rates"))
        self.assertIn('data-panel="def" class="tab-panel"', content)
        self.assertIn('data-panel="cast" class="tab-panel hidden', content)

    def test_def_tab_renders_rate_table_and_form(self):
        content = self._get(reverse("rates"))
        self.assertIn('id="rates-def"', content)
        self.assertIn('id="defAddForm"', content)

    def test_cast_tab_renders_content(self):
        content = self._get(reverse("rates") + "?tab=cast")
        self.assertIn('data-panel="cast" class="tab-panel"', content)
        self.assertIn('id="rates-cast"', content)
        self.assertIn('id="castAddForm"', content)

    def test_reg_tab_renders_content(self):
        content = self._get(reverse("rates") + "?tab=reg")
        self.assertIn('data-panel="reg" class="tab-panel"', content)
        self.assertIn('id="rates-reg"', content)
        self.assertIn('id="regAddForm"', content)

    def test_summoner_tab_renders_content(self):
        content = self._get(reverse("rates") + "?tab=summoner")
        self.assertIn('data-panel="summoner" class="tab-panel"', content)
        self.assertIn('id="summoner"', content)
        self.assertIn("Надбавка за суммонеров", content)

    def test_post_add_rate_redirects_and_creates(self):
        response = self.client.post(
            reverse("rates"),
            {
                "add_rate": "1",
                "start_time": "08:00",
                "end_time": "16:00",
                "rate_kk": "75.00",
            },
        )
        self.assertRedirects(response, reverse("rates"))
        rate = Rate.objects.get(start_time=time(8, 0), end_time=time(16, 0))
        self.assertEqual(rate.rate_kk, Decimal("75.00"))
        self.assertTrue(rate.active)

    def test_post_edit_rate_redirects_and_updates(self):
        Rate.objects.all().delete()
        rate = Rate.objects.create(
            start_time=time(0, 1),
            end_time=time(8, 0),
            rate_kk=Decimal("100"),
        )
        response = self.client.post(
            reverse("rates"),
            {
                "edit_rate": str(rate.pk),
                "start_time": "09:00",
                "end_time": "17:00",
                "rate_kk": "80",
            },
        )
        self.assertRedirects(response, reverse("rates"))
        rate.refresh_from_db()
        self.assertEqual(rate.start_time, time(9, 0))
        self.assertEqual(rate.end_time, time(17, 0))
        self.assertEqual(rate.rate_kk, Decimal("80"))

    def test_post_delete_rate_redirects_and_deletes(self):
        Rate.objects.all().delete()
        rate = Rate.objects.create(
            start_time=time(0, 1),
            end_time=time(8, 0),
            rate_kk=Decimal("100"),
        )
        response = self.client.post(reverse("rates"), {"delete_rate": str(rate.pk)})
        self.assertRedirects(response, reverse("rates"))
        self.assertEqual(Rate.objects.count(), 0)

    def test_get_edit_redirects_from_settings_to_rates(self):
        response = self.client.get(reverse("settings") + "?edit=123")
        self.assertRedirects(response, reverse("rates") + "?tab=def&edit=123")

    def test_get_edit_cast_redirects_from_settings_to_rates(self):
        response = self.client.get(reverse("settings") + "?edit_cast=123")
        self.assertRedirects(response, reverse("rates") + "?tab=cast&edit_cast=123")

    def test_get_tab_reg_redirects_from_settings_to_rates(self):
        response = self.client.get(reverse("settings") + "?tab=reg")
        self.assertRedirects(response, reverse("rates") + "?tab=reg")

    def test_post_save_summoner_bonus_from_settings_stays_on_settings(self):
        response = self.client.post(
            reverse("settings"),
            {"save_summoner_bonus": "1", "is_enabled": "on", "percent": "3.5"},
        )
        self.assertRedirects(response, reverse("rates"))

    def test_settings_page_still_shows_tiles(self):
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('class="settings-tiles"', content)
        self.assertIn("Тарифы за DEF", content)
