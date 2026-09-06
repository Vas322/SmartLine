"""Tests for the Smartline web interface - RegistrationSettingsTests class."""
import re
from datetime import time, timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import (
    Activity,
    CastRate,
    Instruction,
    Player,
    Rate,
    Registration,
    RegistrationRate,
    ScheduleMirror,
    TelegramMessage,
)

_XLSX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)



class RegistrationSettingsTests(TestCase):
    """Tests for RegistrationRate CRUD in settings."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="kl",
            password="test-password-123",
            is_staff=True,
        )
        # Clear any seeded registration rates
        RegistrationRate.objects.all().delete()

    def _login(self):
        self.client.login(username="kl", password="test-password-123")

    def test_settings_shows_registration_rates_section(self):
        self._login()
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Тарифы за регистрацию", content)

    def test_settings_add_registration_rate(self):
        self._login()
        response = self.client.post(
            reverse("settings"),
            {
                "add_reg_rate": "1",
                "start_time": "08:00",
                "end_time": "16:00",
                "rate_kk": "15.00",
            },
        )
        self.assertRedirects(response, reverse("settings"))
        rate = RegistrationRate.objects.get(start_time=time(8, 0), end_time=time(16, 0))
        self.assertEqual(rate.rate_kk, Decimal("15.00"))
        self.assertTrue(rate.active)
        self.assertEqual(rate.order, 0)

    def test_settings_edit_registration_rate(self):
        self._login()
        rate = RegistrationRate.objects.create(
            start_time=time(0, 1),
            end_time=time(8, 0),
            rate_kk=Decimal("10.00"),
            order=1,
        )

        response = self.client.get(reverse("settings") + f"?edit_reg={rate.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="edit_reg_rate"', response.content.decode())

        response = self.client.post(
            reverse("settings"),
            {
                "edit_reg_rate": str(rate.pk),
                "start_time": "09:00",
                "end_time": "17:00",
                "rate_kk": "25.00",
            },
        )
        self.assertRedirects(response, reverse("settings"))

        rate.refresh_from_db()
        self.assertEqual(rate.start_time, time(9, 0))
        self.assertEqual(rate.end_time, time(17, 0))
        self.assertEqual(rate.rate_kk, Decimal("25.00"))
        self.assertEqual(RegistrationRate.objects.count(), 1)

    def test_settings_delete_registration_rate(self):
        self._login()
        rate = RegistrationRate.objects.create(
            start_time=time(0, 1),
            end_time=time(8, 0),
            rate_kk=Decimal("10.00"),
        )
        response = self.client.post(
            reverse("settings"),
            {"delete_reg_rate": str(rate.pk)},
        )
        self.assertRedirects(response, reverse("settings"))
        self.assertEqual(RegistrationRate.objects.count(), 0)

    def test_settings_registration_rate_form_hidden_by_default(self):
        self._login()
        response = self.client.get(reverse("settings"))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('id="regAddForm"', content)
        self.assertIn(
            '<button type="button" class="btn" data-toggle-form="regAddForm">',
            content,
        )
        self.assertRegex(content, r'id="regAddForm"[^>]*\shidden')
