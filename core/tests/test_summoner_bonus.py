"""Tests for the SummonerBonusSettings model and PlayerEditForm summoner_count."""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from core.forms import PlayerEditForm
from core.models import Player, SummonerBonusSettings
from core.services import summoner_bonus_service


class SummonerBonusSettingsModelTests(TestCase):
    """Singleton model: get_or_create(pk=1) and defaults."""

    def test_get_settings_creates_singleton_with_defaults(self):
        settings = summoner_bonus_service.get_settings()
        self.assertEqual(settings.pk, 1)
        self.assertFalse(settings.is_enabled)
        self.assertEqual(settings.percent, Decimal("0.5"))

    def test_singleton_is_single_instance(self):
        summoner_bonus_service.get_settings()
        summoner_bonus_service.get_settings()
        self.assertEqual(SummonerBonusSettings.objects.count(), 1)

    def test_defaults_on_created_instance(self):
        settings = SummonerBonusSettings()
        self.assertFalse(settings.is_enabled)
        self.assertEqual(settings.percent, Decimal("0.5"))

    def test_percent_validators(self):
        settings = SummonerBonusSettings(percent=Decimal("0.5"))
        # Значения в пределах 0..100 проходят.
        settings.full_clean()
        # Вне диапазона — ошибка.
        for bad in (Decimal("-1"), Decimal("100.01")):
            settings.percent = bad
            with self.assertRaises(ValidationError):
                settings.full_clean()


class PlayerEditFormSummonerCountTests(TestCase):
    """PlayerEditForm: summoner_count validation."""

    def setUp(self):
        self.player = Player.objects.create(nickname="Swettka")

    def _form(self, **data):
        values = {
            "nickname": "Swettka",
            "summoner_count": "0",
        }
        values.update(data)
        return PlayerEditForm(values, instance=self.player)

    def test_zero_is_valid(self):
        form = self._form(summoner_count="0")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["summoner_count"], 0)

    def test_positive_value_is_valid(self):
        form = self._form(summoner_count="3")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["summoner_count"], 3)

    def test_above_max_is_invalid(self):
        form = self._form(summoner_count="100")
        self.assertFalse(form.is_valid())
        self.assertIn("summoner_count", form.errors)

    def test_negative_is_invalid(self):
        form = self._form(summoner_count="-1")
        self.assertFalse(form.is_valid())
        self.assertIn("summoner_count", form.errors)

    def test_empty_becomes_zero(self):
        form = self._form(summoner_count="")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["summoner_count"], 0)
