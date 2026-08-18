"""Data models for the Smartline core module."""
from django.conf import settings
from django.db import models


class Player(models.Model):
    nickname = models.CharField(max_length=64, unique=True)
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.nickname


class TelegramMessage(models.Model):
    class Status(models.TextChoices):
        PROCESSED = "PROCESSED", "Processed"
        ERROR = "ERROR", "Error"
        IGNORED = "IGNORED", "Ignored"

    telegram_chat_id = models.BigIntegerField()
    telegram_message_id = models.BigIntegerField()
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    telegram_username = models.CharField(max_length=64, blank=True)
    text = models.TextField()
    message_date = models.DateTimeField()
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


class Activity(models.Model):
    class ActivityType(models.TextChoices):
        DEF = "DEF", "DEF"
        FARM = "FARM", "FARM"

    player = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    telegram_message = models.ForeignKey(
        TelegramMessage,
        on_delete=models.PROTECT,
        related_name="activities",
    )
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    activity_type = models.CharField(max_length=8, choices=ActivityType.choices)
    wave_start_time = models.TimeField(null=True, blank=True)
    payment_kk = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.player_id} {self.activity_type} {self.amount}"


class ProcessingError(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "New"
        NOTIFIED = "NOTIFIED", "Notified"
        RESOLVED = "RESOLVED", "Resolved"

    telegram_message = models.OneToOneField(
        TelegramMessage,
        on_delete=models.PROTECT,
        related_name="processing_error",
    )
    reason = models.TextField()
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.NEW,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.telegram_message} {self.reason}"


class Setting(models.Model):
    key = models.CharField(max_length=64, unique=True)
    value = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True)

    def __str__(self) -> str:
        return self.key


class Instruction(models.Model):
    slug = models.CharField(max_length=64, unique=True)
    title = models.CharField(max_length=128)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="edited_instructions",
    )

    def __str__(self) -> str:
        return self.title
