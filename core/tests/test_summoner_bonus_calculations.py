"""Tests for summoner bonus calculation."""
from decimal import Decimal

from django.test import TestCase

from core.services import summoner_bonus_service


class SummonerBonusCalculationTests(TestCase):

    def test_basic_bonus(self):
        result = summoner_bonus_service.calculate_bonus(Decimal("50.00"), 10, Decimal("0.50"))
        self.assertEqual(result, Decimal("2.50"))

    def test_rounding_half_up(self):
        result = summoner_bonus_service.calculate_bonus(Decimal("33.333"), 7, Decimal("0.1"))
        self.assertEqual(result, Decimal("0.23"))

    def test_zero_summoners(self):
        result = summoner_bonus_service.calculate_bonus(Decimal("100.00"), 0, Decimal("0.50"))
        self.assertEqual(result, Decimal("0.00"))

    def test_zero_def_payment(self):
        result = summoner_bonus_service.calculate_bonus(Decimal("0.00"), 10, Decimal("0.50"))
        self.assertEqual(result, Decimal("0.00"))

    def test_zero_percent(self):
        result = summoner_bonus_service.calculate_bonus(Decimal("50.00"), 10, Decimal("0.00"))
        self.assertEqual(result, Decimal("0.00"))

    def test_example_from_spec(self):
        base = Decimal("50.00")
        result = summoner_bonus_service.calculate_bonus(base, 10, Decimal("0.50"))
        self.assertEqual(result, Decimal("2.50"))
        self.assertEqual(base + result, Decimal("52.50"))
