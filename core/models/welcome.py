"""Core data models — Part 3: welcome settings for new group members.

Singleton model (pk=1): welcome_text (empty = greetings disabled) and
block_until (pause after a mass join). Accessed via the service helper
`WelcomeSettings.objects.get_or_create(pk=1)`.
"""
from django.db import models


class WelcomeSettings(models.Model):
    """Настройки приветствия новых участников Telegram-группы (однозаписные)."""

    welcome_text = models.TextField(
        blank=True,
        default="",
        verbose_name="Текст приветствия",
        help_text="Пустой текст — приветствия выключены.",
    )
    block_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Блокировка приветствий до",
        help_text="Время окончания паузы после массового захода.",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Создано")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Настройка приветствия"
        verbose_name_plural = "Настройки приветствия"

    def __str__(self) -> str:
        return "Настройка приветствия"
