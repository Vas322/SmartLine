"""Core data models — Part 7: global summoner bonus settings.

Singleton model (pk=1): a paid bonus per summoner. This stage only stores
the data and settings; calculation is out of scope. Accessed via the
service helper `SummonerBonusSettings.objects.get_or_create(pk=1)`.
"""
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class SummonerBonusSettings(models.Model):
    """Глобальная надбавка за суммонеров (singleton pk=1)."""

    is_enabled = models.BooleanField(
        default=False,
        verbose_name="Надбавка включена",
    )
    percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.5"),
        verbose_name="Процент за 1 суммонера",
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
    )
    enabled_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Дата включения",
        help_text="Надбавка применяется только к активностям с датой >= этой дате. "
                   "Не меняйте вручную без необходимости.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Надбавка за суммонеров"
        verbose_name_plural = "Надбавка за суммонеров"

    def __str__(self) -> str:
        return "Надбавка за суммонеров"
