"""Tests for the deterministic activity message parser."""
from datetime import time
from decimal import Decimal

from django.test import SimpleTestCase

from core.parsers import ParserError, parse_activity_message, parse_registration_message


class ParseActivityMessageTests(SimpleTestCase):
    def test_basic_def(self):
        parsed = parse_activity_message("+1 | деф | Swettka | 11.56 | Первая волна")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertFalse(parsed.has_cast)
        self.assertEqual(parsed.nickname, "Swettka")
        self.assertEqual(parsed.description, "Первая волна")
        self.assertEqual(parsed.wave_start, time(11, 56))

    def test_comma_decimal_separator(self):
        parsed = parse_activity_message("+0,5 | деф | Swettka | 11.56 | Первая волна")
        self.assertEqual(parsed.amount, Decimal("0.5"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nickname, "Swettka")
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
        self.assertEqual(parsed.nickname, "Swettka")
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
        self.assertFalse(parsed.has_cast)

    def test_farm_type(self):
        parsed = parse_activity_message("+2 | фарм | Swettka | 11.56 | Две волны")
        self.assertEqual(parsed.amount, Decimal("2"))
        self.assertEqual(parsed.activity_type, "FARM")
        self.assertFalse(parsed.has_cast)

    def test_leading_spaces(self):
        parsed = parse_activity_message("  +1 | деф | Swettka | 11.56 | описание")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.nickname, "Swettka")

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
        self.assertEqual(str(ctx.exception), "unknown_activity_type")

    def test_empty_activity_type(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | | Swettka | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "unknown_activity_type")

    def test_empty_nickname(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "empty_nickname")

    def test_five_parts_without_description(self):
        parsed = parse_activity_message("+1 | деф | Swettka | 11.56 |")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nickname, "Swettka")
        self.assertEqual(parsed.description, "")

    def test_four_fields_no_description_parses(self):
        parsed = parse_activity_message("+1 - деф - presli - 13:00")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nickname, "presli")
        self.assertEqual(parsed.wave_start, time(13, 0))
        self.assertEqual(parsed.description, "")

    def test_no_separators(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 деф Swettka описание")
        self.assertEqual(str(ctx.exception), "missing_field_separators")

    def test_no_separators_uses_smart_error(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 деф Polako Attacker 13.00")
        self.assertEqual(str(ctx.exception), "missing_field_separators")

    def test_empty_description_allowed(self):
        parsed = parse_activity_message("+1 | деф | Swettka | 11.56 |")
        self.assertEqual(parsed.description, "")
        self.assertEqual(parsed.amount, Decimal("1"))

    def test_missing_wave_time(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | Swettka")
        self.assertEqual(str(ctx.exception), "missing_wave_time")

    def test_missing_activity_type_when_type_omitted(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 - Росомаха - 20.00 текст для теста вот такое сообщение")
        self.assertEqual(str(ctx.exception), "missing_activity_type")

    def test_missing_activity_type_with_pipe_separators(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | Росомаха | 20.00")
        self.assertEqual(str(ctx.exception), "missing_activity_type")

    def test_missing_nickname_when_type_and_time_present(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | 20.00")
        self.assertEqual(str(ctx.exception), "empty_nickname")

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
        self.assertEqual(parsed.nickname, "Swettka")
        self.assertEqual(parsed.description, "Первая волна")
        self.assertEqual(parsed.wave_start, time(11, 56))

    def test_em_dash_separator(self):
        parsed = parse_activity_message("+0,5—деф—Swettka—11.56—описание")
        self.assertEqual(parsed.amount, Decimal("0.5"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nickname, "Swettka")

    def test_en_dash_separator(self):
        parsed = parse_activity_message("+2–фарм–Swettka–11.56–две волны")
        self.assertEqual(parsed.amount, Decimal("2"))
        self.assertEqual(parsed.activity_type, "FARM")
        self.assertEqual(parsed.nickname, "Swettka")

    def test_mixed_separators(self):
        parsed = parse_activity_message("+1|деф-Swettka|11.56|описание")
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertEqual(parsed.nickname, "Swettka")
        self.assertEqual(parsed.description, "описание")

    def test_description_keeps_separator_chars(self):
        parsed = parse_activity_message("+1-деф-Swettka-11.56-описание с дефисом-тест")
        self.assertEqual(parsed.nickname, "Swettka")
        self.assertEqual(parsed.description, "описание с дефисом-тест")

    def test_hyphen_uppercase_type(self):
        parsed = parse_activity_message("+1—ДЕФ—Swettka—11.56—описание")
        self.assertEqual(parsed.activity_type, "DEF")

    def test_invalid_nickname_with_space(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | Swett ka | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "invalid_nickname")

    def test_invalid_nickname_with_symbol(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | Swettka! | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "invalid_nickname")

    def test_two_nicks_via_space_is_invalid(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф | Swettka Pocomaxa | 11.56 | описание")
        self.assertEqual(str(ctx.exception), "invalid_nickname")

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
        self.assertEqual(str(ctx.exception), "unknown_activity_type")

    def test_wave_time_flexible_description_after_time(self):
        parsed = parse_activity_message(
            "+1 - farm - Pocomaxa - 18:00. Тестовое сообщение"
        )
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.activity_type, "FARM")
        self.assertEqual(parsed.nickname, "Pocomaxa")
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

    # --- compound activity types (каст / перекаст) ---

    def test_def_plus_cast(self):
        parsed = parse_activity_message("+1 | деф+каст | Swettka | 11.56 | Первая волна")
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertTrue(parsed.has_cast)
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.nickname, "Swettka")
        self.assertEqual(parsed.wave_start, time(11, 56))

    def test_standalone_cast(self):
        parsed = parse_activity_message("+0,3 | каст | Swettka | 11.56 | Первая волна")
        self.assertEqual(parsed.activity_type, "CAST")
        self.assertTrue(parsed.has_cast)
        self.assertEqual(parsed.amount, Decimal("0.3"))

    def test_farm_plus_cast(self):
        parsed = parse_activity_message("+1 | фарм+каст | presli | 11:56")
        self.assertEqual(parsed.activity_type, "FARM")
        self.assertTrue(parsed.has_cast)
        self.assertEqual(parsed.amount, Decimal("1"))
        self.assertEqual(parsed.wave_start, time(11, 56))

    def test_english_tokens_lowercase(self):
        parsed = parse_activity_message("+1 | def+cast | Swettka | 11.56 | описание")
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertTrue(parsed.has_cast)

    def test_uppercase_compound(self):
        parsed = parse_activity_message("+1 | ДЕФ+КАСТ | Swettka | 11.56")
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertTrue(parsed.has_cast)

    def test_uppercase_cast(self):
        parsed = parse_activity_message("+1 | КАСТ | Swettka | 11.56")
        self.assertEqual(parsed.activity_type, "CAST")
        self.assertTrue(parsed.has_cast)

    def test_recast_identical_to_cast(self):
        parsed = parse_activity_message("+1 | деф+перекаст | Swettka | 11.56")
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertTrue(parsed.has_cast)

    def test_recast_english_identical_to_cast(self):
        parsed = parse_activity_message("+1 | recast | Swettka | 11.56")
        self.assertEqual(parsed.activity_type, "CAST")
        self.assertTrue(parsed.has_cast)

    def test_whitespace_and_plus_combined(self):
        parsed = parse_activity_message("+1 | деф  +  каст | Swettka | 11.56")
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertTrue(parsed.has_cast)

    def test_whitespace_separated_tokens(self):
        parsed = parse_activity_message("+1 | фарм каст | Swettka | 11.56")
        self.assertEqual(parsed.activity_type, "FARM")
        self.assertTrue(parsed.has_cast)

    def test_no_spaces_around_separators_compound(self):
        parsed = parse_activity_message("+1|деф+каст|  Swettka |11.56")
        self.assertEqual(parsed.activity_type, "DEF")
        self.assertTrue(parsed.has_cast)
        self.assertEqual(parsed.nickname, "Swettka")
        self.assertEqual(parsed.wave_start, time(11, 56))

    def test_def_farm_conflict(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф+фарм | Swettka")
        self.assertEqual(str(ctx.exception), "def_and_farm_conflict")

    def test_unknown_type_token(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | блабла | Swettka")
        self.assertEqual(str(ctx.exception), "unknown_activity_type")

    def test_duplicate_same_token(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | каст+каст | Swettka")
        self.assertEqual(str(ctx.exception), "duplicate_type")

    def test_duplicate_def_tokens(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф+деф | Swettka | 11.56")
        self.assertEqual(str(ctx.exception), "duplicate_type")

    def test_duplicate_cast_recast(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | каст+recast | Swettka | 11.56")
        self.assertEqual(str(ctx.exception), "duplicate_type")

    def test_unknown_token_in_compound(self):
        with self.assertRaises(ParserError) as ctx:
            parse_activity_message("+1 | деф+блабла | Swettka | 11.56")
        self.assertEqual(str(ctx.exception), "unknown_activity_type")


class ParseRegistrationMessageTests(SimpleTestCase):
    """Tests for the registration message parser."""

    def test_basic_registration_lowercase(self):
        parsed = parse_registration_message("рега 2 кланами атака форта")
        self.assertEqual(parsed.clans_count, 2)
        self.assertEqual(parsed.description, "атака форта")

    def test_basic_registration_uppercase(self):
        parsed = parse_registration_message("РЕГА 3 кланов")
        self.assertEqual(parsed.clans_count, 3)
        self.assertEqual(parsed.description, "")

    def test_registration_full_word(self):
        parsed = parse_registration_message("регистрация 1 клан описание")
        self.assertEqual(parsed.clans_count, 1)
        self.assertEqual(parsed.description, "описание")

    def test_registration_mixed_case(self):
        parsed = parse_registration_message("РеГа 5 кланов тест")
        self.assertEqual(parsed.clans_count, 5)
        self.assertEqual(parsed.description, "тест")

    def test_registration_extra_spaces(self):
        parsed = parse_registration_message("  рега   2   клана   описание  ")
        self.assertEqual(parsed.clans_count, 2)
        self.assertEqual(parsed.description, "описание")

    def test_registration_no_description(self):
        parsed = parse_registration_message("регистрация 4 клана")
        self.assertEqual(parsed.clans_count, 4)
        self.assertEqual(parsed.description, "")

    def test_registration_missing_keyword_raises(self):
        with self.assertRaises(ParserError) as ctx:
            parse_registration_message("2 клана атака")
        self.assertEqual(str(ctx.exception), "registration_missing_keyword")

    def test_registration_missing_clans_count_raises(self):
        with self.assertRaises(ParserError) as ctx:
            parse_registration_message("рега")
        self.assertEqual(str(ctx.exception), "registration_missing_clans_count")

    def test_registration_invalid_clans_count_zero_raises(self):
        with self.assertRaises(ParserError) as ctx:
            parse_registration_message("рега 0 кланов")
        self.assertEqual(str(ctx.exception), "registration_invalid_clans_count")

    def test_registration_invalid_clans_count_negative_raises(self):
        with self.assertRaises(ParserError) as ctx:
            parse_registration_message("рега -1 кланов")
        self.assertEqual(str(ctx.exception), "registration_invalid_clans_count")

    def test_registration_invalid_clans_count_non_number_raises(self):
        with self.assertRaises(ParserError) as ctx:
            parse_registration_message("рега много кланов")
        self.assertEqual(str(ctx.exception), "registration_invalid_clans_count")

    def test_registration_empty_raises(self):
        with self.assertRaises(ParserError) as ctx:
            parse_registration_message("")
        self.assertEqual(str(ctx.exception), "registration_empty")

    def test_registration_keyword_not_at_start_raises(self):
        with self.assertRaises(ParserError) as ctx:
            parse_registration_message("привет рега 2 клана")
        self.assertEqual(str(ctx.exception), "registration_missing_keyword")

    def test_registration_keyword_as_substring_raises(self):
        with self.assertRaises(ParserError) as ctx:
            parse_registration_message("регалия 2 клана")
        self.assertEqual(str(ctx.exception), "registration_missing_keyword")