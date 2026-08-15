"""Tests for the deterministic activity message parser."""
from decimal import Decimal

from django.test import SimpleTestCase

from core.parsers import ParserError, parse_activity_message


class ParseActivityMessageTests(SimpleTestCase):
    def test_basic_def(self):
        parsed = parse_activity_message("+1 | деф | Swettka | Первая волна")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])
        self.assertEqual(parsed.description, "Первая волна")

    def test_comma_decimal_separator(self):
        parsed = parse_activity_message("+0,5 | деф | Swettka | Первая волна")
        self.assertEqual(parsed.amount, Decimal("0.5"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])

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
        self.assertEqual(parsed.nicknames, ["Swettka"])
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
        self.assertEqual(parsed.nicknames, ["Swettka"])

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

    def test_three_parts_without_description(self):
        parsed = parse_activity_message("+1 | деф | Swettka")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])
        self.assertEqual(parsed.description, "")

    def test_no_separators(self):
        with self.assertRaises(ParserError):
            parse_activity_message("+1 деф Swettka описание")

    def test_empty_description_allowed(self):
        parsed = parse_activity_message("+1 | деф | Swettka |")
        self.assertEqual(parsed.description, "")
        self.assertEqual(parsed.amount, Decimal("1"))

    def test_hyphen_separator(self):
        parsed = parse_activity_message("+1-деф-Swettka-Первая волна")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])
        self.assertEqual(parsed.description, "Первая волна")

    def test_em_dash_separator(self):
        parsed = parse_activity_message("+0,5—деф—Swettka—описание")
        self.assertEqual(parsed.amount, Decimal("0.5"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])

    def test_en_dash_separator(self):
        parsed = parse_activity_message("+2–фарм–Swettka–две волны")
        self.assertEqual(parsed.amount, Decimal("2"))
        self.assertEqual(parsed.activity_type, "FARM")
        self.assertEqual(parsed.nicknames, ["Swettka"])

    def test_mixed_separators(self):
        parsed = parse_activity_message("+1|деф-Swettka|описание")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])
        self.assertEqual(parsed.description, "описание")

    def test_description_keeps_separator_chars(self):
        parsed = parse_activity_message("+1-деф-Swettka-описание с дефисом-тест")
        self.assertEqual(parsed.nicknames, ["Swettka"])
        self.assertEqual(parsed.description, "описание с дефисом-тест")

    def test_hyphen_uppercase_type(self):
        parsed = parse_activity_message("+1—ДЕФ—Swettka—описание")
        self.assertEqual(parsed.activity_type, "DEF")

    def test_multi_nickname_comma_separated(self):
        parsed = parse_activity_message(
            "+1 - деф - Swettka, Pocomaxa - Первая волна"
        )
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka", "Pocomaxa"])
        self.assertEqual(parsed.description, "Первая волна")

    def test_multi_nickname_spaces_around_commas(self):
        parsed = parse_activity_message("+1|деф|Swettka, Pocomaxa | волна")
        self.assertEqual(parsed.nicknames, ["Swettka", "Pocomaxa"])
        self.assertEqual(parsed.description, "волна")

    def test_multi_nickname_no_spaces_around_commas(self):
        parsed = parse_activity_message("+1|деф|Swettka,Pocomaxa|волна")
        self.assertEqual(parsed.nicknames, ["Swettka", "Pocomaxa"])
        self.assertEqual(parsed.description, "волна")

    def test_multi_nickname_dedup_case_insensitive(self):
        parsed = parse_activity_message("+1 - деф - Swettka, swettka - в")
        self.assertEqual(parsed.nicknames, ["Swettka"])

    def test_multi_nickname_keeps_first_spelling_on_dedup(self):
        parsed = parse_activity_message("+1 - деф - swettka, Swettka - в")
        self.assertEqual(parsed.nicknames, ["swettka"])

    def test_empty_nicknames_after_split(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | ,  | описание")
        self.assertEqual(str(ctx.exception), "empty_nickname")

    def test_empty_nickname_parameter_raises(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | | описание")
        self.assertEqual(str(ctx.exception), "empty_nickname")

    def test_user_example_without_description(self):
        parsed = parse_activity_message("+0,5 | фарм | Ostin, Pocomaxa")
        self.assertEqual(parsed.amount, Decimal("0.5"))
        self.assertEqual(parsed.activity_type, "FARM")
        self.assertEqual(parsed.nicknames, ["Ostin", "Pocomaxa"])
        self.assertEqual(parsed.description, "")

    def test_wrong_order_type_first(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+фарм | 0,5 | Ostin")
        self.assertEqual(str(ctx.exception), "invalid_amount")

    def test_wrong_order_nickname_first(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+Ostin | фарм | 0,5")
        self.assertEqual(str(ctx.exception), "invalid_amount")

    def test_wrong_order_type_in_nick_position(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+0,5 | Ostin | фарм")
        self.assertEqual(str(ctx.exception), "invalid_activity_type")
