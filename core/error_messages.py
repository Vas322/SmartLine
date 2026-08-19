"""Human-readable Russian messages for internal processing-error reasons.

The raw reason code is still stored in the database (ProcessingError.reason)
and logged for audit; this module only controls what the end user sees.
"""

ERROR_MESSAGES = {
    "invalid_amount": "Не удалось разобрать количество часов. Укажите его сразу после «+» (например, +1 или +0,5).",
    "invalid_activity_type": "Неизвестный тип активности. Используйте «деф» (оплачивается) или «фарм» (учитывается без оплаты).",
    "invalid_wave_time": "Время начала волны указано неверно. Формат: ЧЧ.ММ или ЧЧ:ММ, например 13.00 или 21:30.",
    "missing_field_separators": "Не найдены разделители между полями. Используйте «|» или «-» между полями: количество | тип | ник | время, например: +1 | деф | Ник | 13.00",
    "missing_activity_type": "Не указан тип активности. Используйте «деф» (оплачивается) или «фарм» (учитывается без оплаты). Формат: +количество | деф/фарм | ник | время",
    "missing_wave_time": "Не указано время начала волны. Добавьте его после ника в формате ЧЧ.ММ, например: +1 | деф | Ник | 13.00",
    "empty_nickname": "Не указан ник игрока. Формат: +ЧЧ.ММ | деф/фарм | Ник | ЧЧ.ММ",
    "message_does_not_start_with_plus": "Сообщение должно начинаться с «+». Пример: +1 | деф | Ник | 13.00",
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