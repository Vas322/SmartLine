"""Tests for the deterministic activity message parser."""
from decimal import Decimal

from django.test import SimpleTestCase

from core.parsers import ParserError, parse_activity_message


class ParseActivityMessageTests(SimpleTestCase):
    def test_basic_def(self):
        parsed = parse_activity_message("+1 | деф | Swettka | Первая волна")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nickname, "Swettka")
        self.assertEqual(parsed.description, "Первая волна")

    def test_comma_decimal_separator(self):
        parsed = parse_activity_message("+0,5 | деф | Swettka | Первая волна")
        self.assertEqual(parsed.amount, Decimal("0.5"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nickname, "Swettka")

    def test_dot_decimal_separator(self):
        parsed = parse_activity_message("+0.5 | деф | Swettka | Первая волна")
        self.assertEqual(parsed.amount, Decimal("0.5"))

    def test_three_tenths(self):
        parsed = parse_activity_message("+0,3 | деф | Swettka | Частичная волна")
        self.assertEqual(parsed.amount, Decimal("0.3"))
        self.assertEqual(parsed.description, "Частичная волна")

    def test_two_hours(self):
        parsed = parse_activity_message("+2 | деф | Swettka | Два часа")
        self.assertEqual(parsed.amount, Decimal("2"))
        self.assertEqual(parsed.description, "Два часа")

    def test_no_spaces_around_separators(self):
        parsed = parse_activity_message("+1|деф|Swettka|Описание")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nickname, "Swettka")
        self.assertEqual(parsed.description, "Описание")

    def test_uppercase_type(self):
        parsed = parse_activity_message("+1 | ДЕФ | Swettka | Описание")
        self.assertEqual(parsed.activity_type, "DEF")

    def test_farm_type(self):
        parsed = parse_activity_message("+2 | фарм | Swettka | Две волны")
        self.assertEqual(parsed.amount, Decimal("2"))
        self.assertEqual(parsed.activity_type, "FARM")

    def test_leading_spaces(self):
        parsed = parse_activity_message("  +1 | деф | Swettka | описание")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.nickname, "Swettka")

    def test_extra_separators_kept_in_description(self):
        parsed = parse_activity_message("+1 | деф | Swettka | описание | лишнее")
        self.assertEqual(parsed.description, "описание | лишнее")

    def test_space_after_plus(self):
        parsed = parse_activity_message("+ 1 | деф | Swettka | описание")
        self.assertEqual(parsed.amount, Decimal("1"))

    def test_negative_is_not_activity(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("-1 | деф | Swettka | описание")
        self.assertEqual(str(ctx.exception), "message_does_not_start_with_plus")

    def test_invalid_amount_text(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+abc | деф | Swettka | описание")
        self.assertEqual(str(ctx.exception), "invalid_amount")

    def test_invalid_amount_zero(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+0 | деф | Swettka | описание")
        self.assertEqual(str(ctx.exception), "invalid_amount")

    def test_invalid_amount_empty(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+ | деф | Swettka | описание")
        self.assertEqual(str(ctx.exception), "invalid_amount")

    def test_invalid_activity_type(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | неизвестный_тип | Swettka | описание")
        self.assertEqual(str(ctx.exception), "invalid_activity_type")

    def test_empty_activity_type(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | | Swettka | описание")
        self.assertEqual(str(ctx.exception), "invalid_activity_type")

    def test_empty_nickname(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | | описание")
        self.assertEqual(str(ctx.exception), "empty_nickname")

    def test_too_few_fields(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | Swettka")
        self.assertEqual(str(ctx.exception), "invalid_format")

    def test_no_separators(self):
        with self.assertRaises(ParserError):
            parse_activity_message("+1 деф Swettka описание")

    def test_empty_description_allowed(self):
        parsed = parse_activity_message("+1 | деф | Swettka |")
        self.assertEqual(parsed.description, "")
        self.assertEqual(parsed.amount, Decimal("1"))
