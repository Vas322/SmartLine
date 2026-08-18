"""Tests for the deterministic activity message parser."""
from datetime import time
from decimal import Decimal

from django.test import SimpleTestCase

from core.parsers import ParserError, parse_activity_message


class ParseActivityMessageTests(SimpleTestCase):
    def test_basic_def(self):
        parsed = parse_activity_message("+1 | деф | Swettka | 11.56 | Первая волна")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])
        self.assertEqual(parsed.description, "Первая волна")
        self.assertEqual(parsed.wave_start, time(11, 56))

    def test_comma_decimal_separator(self):
        parsed = parse_activity_message("+0,5 | деф | Swettka | 11.56 | Первая волна")
        self.assertEqual(parsed.amount, Decimal("0.5"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])
        self.assertEqual(parsed.wave_start, time(11, 56))

    def test_dot_decimal_separator(self):
        parsed = parse_activity_message("+0.5 | деф | Swettka | 11.56 | Первая волна")
        self.assertEqual(parsed.amount, Decimal("0.5"))
        self.assertEqual(parsed.wave_start, time(11, 56))

    def test_three_tenths(self):
        parsed = parse_activity_message("+0,3 | деф | Swettka | 11.56 | Частичная волна")
        self.assertEqual(parsed.amount, Decimal("0.3"))
        self.assertEqual(parsed.description, "Частичная волна")

    def test_two_hours(self):
        parsed = parse_activity_message("+2 | деф | Swettka | 11.56 | Два часа")
        self.assertEqual(parsed.amount, Decimal("2"))
        self.assertEqual(parsed.description, "Два часа")

    def test_no_spaces_around_separators(self):
        parsed = parse_activity_message("+1|деф|Swettka|11.56|Описание")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])
        self.assertEqual(parsed.description, "Описание")
        self.assertEqual(parsed.wave_start, time(11, 56))

    def test_colon_time_separator(self):
        parsed = parse_activity_message("+1 | деф | Swettka | 11:56 | Описание")
        self.assertEqual(parsed.wave_start, time(11, 56))

    def test_single_digit_hour(self):
        parsed = parse_activity_message("+1 | деф | Swettka | 9.05 | Описание")
        self.assertEqual(parsed.wave_start, time(9, 5))

    def test_uppercase_type(self):
        parsed = parse_activity_message("+1 | ДЕФ | Swettka | 11.56 | Описание")
        self.assertEqual(parsed.activity_type, "DEF")

    def test_farm_type(self):
        parsed = parse_activity_message("+2 | фарм | Swettka | 11.56 | Две волны")
        self.assertEqual(parsed.amount, Decimal("2"))
        self.assertEqual(parsed.activity_type, "FARM")

    def test_leading_spaces(self):
        parsed = parse_activity_message("  +1 | деф | Swettka | 11.56 | описание")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.nicknames, ["Swettka"])

    def test_extra_separators_kept_in_description(self):
        parsed = parse_activity_message("+1 | деф | Swettka | 11.56 | описание | лишнее")
        self.assertEqual(parsed.description, "описание | лишнее")

    def test_space_after_plus(self):
        parsed = parse_activity_message("+ 1 | деф | Swettka | 11.56 | описание")
        self.assertEqual(parsed.amount, Decimal("1"))

    def test_negative_is_not_activity(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("-1 | деф | Swettka | описание")
        self.assertEqual(str(ctx.exception), "message_does_not_start_with_plus")

    def test_invalid_amount_text(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+abc | деф | Swettka | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "invalid_amount")

    def test_invalid_amount_zero(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+0 | деф | Swettka | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "invalid_amount")

    def test_invalid_amount_empty(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+ | деф | Swettka | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "invalid_amount")

    def test_invalid_activity_type(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | неизвестный_тип | Swettka | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "invalid_activity_type")

    def test_empty_activity_type(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | | Swettka | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "invalid_activity_type")

    def test_empty_nickname(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "empty_nickname")

    def test_five_parts_without_description(self):
        parsed = parse_activity_message("+1 | деф | Swettka | 11.56 |")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])
        self.assertEqual(parsed.description, "")

    def test_four_fields_no_description_parses(self):
        parsed = parse_activity_message("+1 - деф - presli - 13:00")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["presli"])
        self.assertEqual(parsed.wave_start, time(13, 0))
        self.assertEqual(parsed.description, "")

    def test_no_separators(self):
        with self.assertRaises(ParserError):
            parse_activity_message("+1 деф Swettka описание")

    def test_empty_description_allowed(self):
        parsed = parse_activity_message("+1 | деф | Swettka | 11.56 |")
        self.assertEqual(parsed.description, "")
        self.assertEqual(parsed.amount, Decimal("1"))

    def test_missing_wave_time(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | Swettka")
        self.assertEqual(str(ctx.exception), "missing_wave_time")

    def test_invalid_wave_time_text(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | Swettka | вечером | описание")
        self.assertEqual(str(ctx.exception), "invalid_wave_time")

    def test_invalid_wave_time_hour_out_of_range(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | Swettka | 24.00 | описание")
        self.assertEqual(str(ctx.exception), "invalid_wave_time")

    def test_invalid_wave_time_minute_out_of_range(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | Swettka | 11.60 | описание")
        self.assertEqual(str(ctx.exception), "invalid_wave_time")

    def test_hyphen_separator(self):
        parsed = parse_activity_message("+1-деф-Swettka-11.56-Первая волна")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])
        self.assertEqual(parsed.description, "Первая волна")
        self.assertEqual(parsed.wave_start, time(11, 56))

    def test_em_dash_separator(self):
        parsed = parse_activity_message("+0,5—деф—Swettka—11.56—описание")
        self.assertEqual(parsed.amount, Decimal("0.5"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])

    def test_en_dash_separator(self):
        parsed = parse_activity_message("+2–фарм–Swettka–11.56–две волны")
        self.assertEqual(parsed.amount, Decimal("2"))
        self.assertEqual(parsed.activity_type, "FARM")
        self.assertEqual(parsed.nicknames, ["Swettka"])

    def test_mixed_separators(self):
        parsed = parse_activity_message("+1|деф-Swettka|11.56|описание")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka"])
        self.assertEqual(parsed.description, "описание")

    def test_description_keeps_separator_chars(self):
        parsed = parse_activity_message("+1-деф-Swettka-11.56-описание с дефисом-тест")
        self.assertEqual(parsed.nicknames, ["Swettka"])
        self.assertEqual(parsed.description, "описание с дефисом-тест")

    def test_hyphen_uppercase_type(self):
        parsed = parse_activity_message("+1—ДЕФ—Swettka—11.56—описание")
        self.assertEqual(parsed.activity_type, "DEF")

    def test_multi_nickname_comma_separated(self):
        parsed = parse_activity_message(
            "+1 - деф - Swettka, Pocomaxa - 11.56 - Первая волна"
        )
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nicknames, ["Swettka", "Pocomaxa"])
        self.assertEqual(parsed.description, "Первая волна")

    def test_multi_nickname_spaces_around_commas(self):
        parsed = parse_activity_message("+1|деф|Swettka, Pocomaxa | 11.56 | волна")
        self.assertEqual(parsed.nicknames, ["Swettka", "Pocomaxa"])
        self.assertEqual(parsed.description, "волна")

    def test_multi_nickname_no_spaces_around_commas(self):
        parsed = parse_activity_message("+1|деф|Swettka,Pocomaxa|11.56|волна")
        self.assertEqual(parsed.nicknames, ["Swettka", "Pocomaxa"])
        self.assertEqual(parsed.description, "волна")

    def test_multi_nickname_dedup_case_insensitive(self):
        parsed = parse_activity_message("+1 - деф - Swettka, swettka - 11.56 - в")
        self.assertEqual(parsed.nicknames, ["Swettka"])

    def test_multi_nickname_keeps_first_spelling_on_dedup(self):
        parsed = parse_activity_message("+1 - деф - swettka, Swettka - 11.56 - в")
        self.assertEqual(parsed.nicknames, ["swettka"])

    def test_empty_nicknames_after_split(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | ,  | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "empty_nickname")

    def test_empty_nickname_parameter_raises(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "empty_nickname")

    def test_user_example_without_description(self):
        parsed = parse_activity_message("+0,5 | фарм | Ostin, Pocomaxa | 11.56 |")
        self.assertEqual(parsed.amount, Decimal("0.5"))
        self.assertEqual(parsed.activity_type, "FARM")
        self.assertEqual(parsed.nicknames, ["Ostin", "Pocomaxa"])
        self.assertEqual(parsed.description, "")

    def test_wrong_order_type_first(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+фарм | 0,5 | Ostin | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "invalid_amount")

    def test_wrong_order_nickname_first(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+Ostin | фарм | 0,5 | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "invalid_amount")

    def test_wrong_order_type_in_nick_position(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+0,5 | Ostin | фарм | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "invalid_activity_type")

    def test_wave_time_flexible_description_after_time(self):
        parsed = parse_activity_message(
            "+1 - farm - Pocomaxa - 18:00. Тестовое сообщение"
        )
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "FARM")
        self.assertEqual(parsed.nicknames, ["Pocomaxa"])
        self.assertEqual(parsed.wave_start, time(18, 0))
        self.assertEqual(parsed.description, "Тестовое сообщение")

    def test_wave_time_flexible_description_without_punctuation(self):
        parsed = parse_activity_message(
            "+1 - farm - Pocomaxa - 18.00 Тестовое сообщение"
        )
        self.assertEqual(parsed.wave_start, time(18, 0))
        self.assertEqual(parsed.description, "Тестовое сообщение")

    def test_wave_time_flexible_no_description(self):
        parsed = parse_activity_message("+1 - farm - Pocomaxa - 18:00")
        self.assertEqual(parsed.wave_start, time(18, 0))
        self.assertEqual(parsed.description, "")

    def test_wave_time_flexible_separate_description_field(self):
        parsed = parse_activity_message(
            "+1 - farm - Pocomaxa - 18:00 - отдельное описание"
        )
        self.assertEqual(parsed.wave_start, time(18, 0))
        self.assertEqual(parsed.description, "отдельное описание")

    def test_wave_time_flexible_rejects_invalid_hour(self):
        with self.assertRaisesRegex(ParserError, "invalid_wave_time"):
            parse_activity_message("+1 - farm - Pocomaxa - 99:99")

    def test_wave_time_flexible_rejects_garbage(self):
        with self.assertRaisesRegex(ParserError, "invalid_wave_time"):
            parse_activity_message("+1 - farm - Pocomaxa - бессмыслица")