"""Human-readable Russian messages for internal processing-error reasons.

The raw reason code is still stored in the database (ProcessingError.reason)
and logged for audit; this module only controls what the end user sees.
"""

ERROR_MESSAGES = {
    "invalid_amount": "Не удалось разобрать количество часов.",
    "invalid_activity_type": "Неизвестный тип активности.",
    "unknown_activity_type": "Неизвестный тип события.",
    "def_and_farm_conflict": "Тип активности не может быть одновременно деф и фарм.",
    "duplicate_type": "Тип активности указан повторно.",
    "invalid_wave_time": "Время начала волны указано неверно.",
    "missing_field_separators": "Не найдены разделители между полями. Используйте «|» или «-»",
    "missing_activity_type": "Не указан тип активности.",
    "missing_wave_time": "Не указано время начала волны.",
    "empty_nickname": "Не указан ник игрока.",
    "message_does_not_start_with_plus": "Сообщение должно начинаться с «+».",
    "invalid_nickname": "Ник может содержать только буквы русского/английского алфавита и цифры. Пожалуйста, исправьте игровой ник на корректный.",
    "nick_already_bound": "Этот ник уже привязан к другому пользователю.",
    # Registration errors
    "registration_empty": "Пустое сообщение регистрации.",
    "registration_missing_keyword": "Сообщение должно начинаться со слова «рега» или «регистрация».",
    "registration_missing_clans_count": "Укажите количество кланов после слова «рега»/«регистрация».",
    "registration_invalid_clans_count": "Количество кланов должно быть целым положительным числом.",
    "registration_no_screenshot": "Регистрация клана без скриншота не принимается к оплате.",
    "registration_unregistered_sender": "Вы не зарегистрированы в системе. Обратитесь к КЛ.",
}


def friendly_error_message(reason: str) -> str:
    """Return a Russian user-facing message for an internal error reason.

    Unknown reasons fall back to a message that still mentions the raw code
    so the clan leader can report it.
    """
    return ERROR_MESSAGES.get(
        reason,
        f"Не удалось обработать сообщение (код: {reason}). Обратитесь к командиру клана.",
    )