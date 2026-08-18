"""Tests for the rate-based payout service."""
from datetime import time
from decimal import Decimal

from django.test import TestCase

from core.models import Rate
from core.services.rates import payment_kk, rate_at


class RateServiceTests(TestCase):
    def setUp(self):
        Rate.objects.all().delete()
        Rate.objects.create(start_time=time(0, 1), end_time=time(8, 0), rate_kk=Decimal("100"), order=1)
        Rate.objects.create(start_time=time(8, 1), end_time=time(16, 0), rate_kk=Decimal("75"), order=2)
        Rate.objects.create(start_time=time(16, 1), end_time=time(0, 0), rate_kk=Decimal("50"), order=3)

    def test_rate_at_boundaries(self):
        self.assertEqual(rate_at(time(8, 0)), Decimal("100"))
        self.assertEqual(rate_at(time(16, 0)), Decimal("75"))
        self.assertEqual(rate_at(time(0, 0)), Decimal("50"))
        self.assertEqual(rate_at(time(0, 1)), Decimal("100"))

    def test_proration(self):
        self.assertEqual(payment_kk(time(7, 30), Decimal("2")), Decimal("162.92"))

    def test_midnight_cross(self):
        self.assertEqual(payment_kk(time(23, 0), Decimal("2")), Decimal("149.17"))

    def test_simple(self):
        self.assertEqual(payment_kk(time(9, 0), Decimal("1")), Decimal("75.00"))