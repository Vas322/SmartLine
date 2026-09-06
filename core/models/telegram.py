"""Core data models — Part 2: Telegram-related models with cross-references.

All Telegram-related models are in one file to avoid circular import issues:
OutgoingMessage references ScheduledMessage (string),
ScheduledMessage references TelegramTopic,
TelegramTopic references TelegramSettings,
and they all need to be imported together.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class TelegramTopic(models.Model):
    """Форумная тема группы для выбора при отправке нового сообщения."""

    group = models.ForeignKey(
        "TelegramSettings",
        on_delete=models.CASCADE,
        related_name="topics",
        verbose_name="Группа",
    )
    name = models.CharField(
        max_length=100,
        verbose_name="Название темы",
    )
    thread_id = models.BigIntegerField(
        verbose_name="ID темы в Telegram",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активна",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создано",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлено",
    )

    class Meta:
        verbose_name = "Телеграм-тема"
        verbose_name_plural = "Телеграм-темы"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["group", "name"],
                name="uniq_topic_name_per_group",
            ),
            models.UniqueConstraint(
                fields=["group", "thread_id"],
                name="uniq_topic_thread_per_group",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class TelegramSettings(models.Model):
    """Группа Telegram, в которую отправляются новые сообщения из веб-интерфейса."""

    name = models.CharField(
        max_length=100,
        verbose_name="Название группы",
    )
    group_chat_id = models.BigIntegerField(
        null=True,
        blank=True,
        unique=True,
        verbose_name="ID группы в Telegram",
        help_text="Числовой ID группы Telegram (например, -1001234567890), в которую отправляются новые сообщения из веб-интерфейса.",
    )
    is_active = models.BooleanField(
        default=False,
        verbose_name="Активная группа",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создано",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлено",
    )

    class Meta:
        verbose_name = "Группа"
        verbose_name_plural = "Группы"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=models.Q(is_active=True),
                name="uniq_active_telegram_group",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ScheduledMessage(models.Model):
    """Сообщение по расписанию, отправляемое автоматически."""

    class Frequency(models.TextChoices):
        WEEKLY = "weekly", "Каждую неделю"
        BIWEEKLY = "biweekly", "Раз в 2 недели"
        MONTHLY = "monthly", "Ежемесячно"
        CUSTOM_DATES = "custom_dates", "Произвольные даты"

    name = models.CharField(
        max_length=100,
        verbose_name="Название",
    )
    text = models.TextField(
        verbose_name="Текст сообщения",
    )
    topic = models.ForeignKey(
        "TelegramTopic",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Тема в Telegram",
    )
    weekdays = models.JSONField(
        default=list,
        verbose_name="Дни недели",
        help_text="Номера дней недели, 0=Пн ... 6=Вс",
    )
    time = models.TimeField(
        verbose_name="Время (MSK)",
    )
    frequency = models.CharField(
        max_length=16,
        choices=Frequency.choices,
        default=Frequency.WEEKLY,
        verbose_name="Частота",
    )
    start_date = models.DateField(
        verbose_name="Дата начала",
        help_text="Первое срабатывание; для 'раз в 2 недели' от неё отсчёт +14 дней",
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата окончания",
    )
    custom_dates = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Конкретные даты",
        help_text="Список дат в формате YYYY-MM-DD",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активно",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Создал",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_scheduled_messages",
        verbose_name="Изменено пользователем",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создано",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="Обновлено",
    )
    last_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Последняя отправка",
    )

    class Meta:
        verbose_name = "Сообщение по расписанию"
        verbose_name_plural = "Сообщения по расписанию"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        """Validate weekdays: list of unique integers in range 0..6."""
        weekdays = self.weekdays or []
        if not isinstance(weekdays, list):
            raise ValidationError({"weekdays": "Дни недели должны быть списком."})
        if not all(isinstance(d, int) and not isinstance(d, bool) and 0 <= d <= 6 for d in weekdays):
            raise ValidationError(
                {"weekdays": "Дни недели должны быть целыми числами от 0 (Пн) до 6 (Вс)."}
            )
        if len(weekdays) != len(set(weekdays)):
            raise ValidationError({"weekdays": "Дни недели не должны повторяться."})
        if self.frequency in (self.Frequency.WEEKLY, self.Frequency.BIWEEKLY) and not weekdays:
            raise ValidationError(
                {"weekdays": "Для периодического расписания укажите хотя бы один день недели."}
            )


class OutgoingMessage(models.Model):
    """Исходящее сообщение, отправленное из веб-интерфейса в Telegram."""

    class Status(models.TextChoices):
        SENT = "SENT", "Отправлено"
        ERROR = "ERROR", "Ошибка"
        PENDING = "PENDING", "В очереди"

    class Source(models.TextChoices):
        MANUAL_REPLY = "manual_reply", "Ручной ответ"
        MANUAL_NEW = "manual_new", "Ручное сообщение"
        SCHEDULED = "scheduled", "Автоматическое"

    telegram_chat_id = models.BigIntegerField(
        verbose_name="ID чата",
    )
    telegram_message_id = models.BigIntegerField(
        verbose_name="ID сообщения в Telegram",
        help_text="ID, присвоенный Telegram при отправке.",
    )
    text = models.TextField(
        verbose_name="Текст",
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outgoing_messages",
        verbose_name="Отправил",
    )
    sent_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Отправлено",
    )
    reply_to_message_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="ID исходного сообщения",
        help_text="ID сообщения, на которое дан ответ (reply).",
    )
    reply_to_text = models.TextField(
        blank=True,
        default="",
        verbose_name="Текст исходного сообщения",
    )
    topic_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Тема",
        help_text="Название темы, в которую отправлено сообщение (для аудита).",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.SENT,
        verbose_name="Статус",
    )
    error_text = models.TextField(
        blank=True,
        default="",
        verbose_name="Текст ошибки",
    )
    source = models.CharField(
        max_length=16,
        choices=Source.choices,
        default=Source.MANUAL_NEW,
        verbose_name="Тип",
    )
    scheduled_message = models.ForeignKey(
        "ScheduledMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Расписание",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Создано",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Исходящее сообщение"
        verbose_name_plural = "Исходящие сообщения"

    def __str__(self) -> str:
        return f"{self.telegram_chat_id}:{self.telegram_message_id} ({self.status})"