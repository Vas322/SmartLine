"""Human-readable Russian messages for internal processing-error reasons.

The raw reason code is still stored in the database (ProcessingError.reason)
and logged for audit; this module only controls what the end user sees.
"""

ERROR_MESSAGES = {
    "invalid_amount": "Не удалось разобрать количество часов.",
    "invalid_activity_type": "Неизвестный тип активности.",
    "invalid_wave_time": "Время начала волны указано неверно.",
    "missing_field_separators": "Не найдены разделители между полями. Используйте «|» или «-»",
    "missing_activity_type": "Не указан тип активности.",
    "missing_wave_time": "Не указано время начала волны.",
    "empty_nickname": "Не указан ник игрока.",
    "message_does_not_start_with_plus": "Сообщение должно начинаться с «+».",
}


def friendly_error_message(reason: str) -> str:
    """Return a Russian user-facing message for an internal error reason.

    Dynamic reasons like 'nickname_registered_to_other_telegram:<nick>'
    are detected by prefix. Unknown reasons fall back to a message that
    still mentions the raw code so the clan leader can report it.
    """
    if reason.startswith("nickname_registered_to_other_telegram:"):
        nick = reason.split(":", 1)[1]
        return f"Ник «{nick}» уже привязан к другому Telegram-аккаунту. Уточните у командира клана."
    return ERROR_MESSAGES.get(
        reason,
        f"Не удалось обработать сообщение (код: {reason}). Обратитесь к командиру клана.",
    )