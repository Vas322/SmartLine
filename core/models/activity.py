"""Core data models — Part 3: activity-related models."""
from django.db import models


class Activity(models.Model):
    class ActivityType(models.TextChoices):
        DEF = "DEF", "DEF"
        FARM = "FARM", "FARM"
        CAST = "CAST", "CAST"

    player = models.ForeignKey(
        "Player",
        on_delete=models.CASCADE,
        related_name="activities",
    )
    telegram_message = models.ForeignKey(
        "TelegramMessage",
        on_delete=models.PROTECT,
        related_name="activities",
    )
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    activity_type = models.CharField(max_length=8, choices=ActivityType.choices)
    has_cast = models.BooleanField(default=False)
    wave_start_time = models.TimeField(null=True, blank=True)
    payment_kk = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
    )
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True, help_text="Время последнего редактирования")

    def __str__(self) -> str:
        return f"{self.player_id} {self.activity_type} {self.amount}"

    @property
    def type_display(self) -> str:
        label = self.get_activity_type_display()
        if self.has_cast and self.activity_type != self.ActivityType.CAST:
            label = f"{label}+CAST"
        return label
    type_display.fget.short_description = "Тип"


class ProcessingError(models.Model):
    class Status(models.TextChoices):
        NEW = "NEW", "New"
        NOTIFIED = "NOTIFIED", "Notified"
        RESOLVED = "RESOLVED", "Resolved"

    telegram_message = models.OneToOneField(
        "TelegramMessage",
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
