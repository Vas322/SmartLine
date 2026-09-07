"""Core data models — Part 1: base models without cross-references."""
from django.db import models


class Player(models.Model):
    nickname = models.CharField(max_length=64, null=True, blank=True)
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    telegram_username = models.CharField(max_length=64, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["telegram_user_id"],
                condition=models.Q(telegram_user_id__isnull=False),
                name="uniq_player_telegram_user_id",
            ),
            models.UniqueConstraint(
                fields=["nickname"],
                condition=models.Q(nickname__isnull=False),
                name="uniq_player_nickname_nonnull",
            ),
        ]

    def __str__(self) -> str:
        return self.nickname or "—"


class TelegramMessage(models.Model):
    class Status(models.TextChoices):
        PROCESSED = "PROCESSED", "Processed"
        ERROR = "ERROR", "Error"
        IGNORED = "IGNORED", "Ignored"
        REGULAR = "REGULAR", "Обычное"

    telegram_chat_id = models.BigIntegerField()
    telegram_message_id = models.BigIntegerField()
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    text = models.TextField()
    original_text = models.TextField(blank=True, default="", help_text="Оригинальный текст до первого редактирования")
    edit_count = models.PositiveIntegerField(default=0, help_text="Количество редактирований")
    edit_history = models.JSONField(default=list, blank=True, help_text="Цепочка предыдущих текстов сообщения")
    message_date = models.DateTimeField()
    message_thread_id = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name="Тема",
        help_text="message_thread_id форумной темы, из которой пришло сообщение (если есть).",
    )
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PROCESSED,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["telegram_chat_id", "telegram_message_id"],
                name="uniq_telegram_chat_message",
            )
        ]

    def __str__(self) -> str:
        return f"{self.telegram_chat_id}:{self.telegram_message_id}"


class Rate(models.Model):
    start_time = models.TimeField()
    end_time = models.TimeField()
    rate_kk = models.DecimalField(max_digits=10, decimal_places=2)
    active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "start_time"]

    def __str__(self) -> str:
        return f"{self.start_time:%H:%M}-{self.end_time:%H:%M}: {self.rate_kk} kk"


class CastRate(models.Model):
    start_time = models.TimeField()
    end_time = models.TimeField()
    rate_kk = models.DecimalField(max_digits=10, decimal_places=2)
    active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "start_time"]

    def __str__(self) -> str:
        return f"{self.start_time:%H:%M}-{self.end_time:%H:%M}: {self.rate_kk} kk"


class RegistrationRate(models.Model):
    """Тариф за регистрацию клана на атаку форта."""
    start_time = models.TimeField()
    end_time = models.TimeField()
    rate_kk = models.DecimalField(max_digits=10, decimal_places=2)
    active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "start_time"]
        verbose_name = "Тариф за регистрацию"
        verbose_name_plural = "Тарифы за регистрацию"

    def __str__(self) -> str:
        return f"{self.start_time:%H:%M}-{self.end_time:%H:%M}: {self.rate_kk} кк"
