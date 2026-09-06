"""Core data models — Part 4: registration models."""
from django.db import models


class Registration(models.Model):
    """Регистрация клана на атаку форта."""
    player = models.ForeignKey(
        "Player",
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    telegram_message = models.OneToOneField(
        "TelegramMessage",
        on_delete=models.PROTECT,
        related_name="registration",
    )
    clans_count = models.PositiveIntegerField()
    payment_kk = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField(blank=True, default="")
    photo_file_id = models.CharField(max_length=255, blank=True, null=True)
    registered_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-registered_at"]

    def __str__(self) -> str:
        return f"{self.player.nickname}: {self.clans_count} кл. — {self.payment_kk} кк"