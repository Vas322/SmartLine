"""Core data models — Part 6: Boss respawn tracking and notifications."""
from django.core.exceptions import ValidationError
from django.db import models

DEFAULT_BOSS_TEMPLATE = (
    "🎮 Сегодня респ Эпик РБ\n\n"
    "Боссы:\n{bosses}\n\n"
    "Окно респа: ~24 часа."
)


class BossRespawn(models.Model):
    """Данные о респе РБ, спарсенные с craft-calc.ru."""

    class BossType(models.TextChoices):
        EPIC = "EPIC", "Эпик РБ"
        SUBCLASS = "SUBCLASS", "Сабкласс РБ"

    boss_name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Название босса",
    )
    boss_type = models.CharField(
        max_length=16,
        choices=BossType.choices,
        verbose_name="Тип босса",
    )
    respawn_start = models.DateTimeField(
        verbose_name="Начало респа (UTC)",
    )
    respawn_end = models.DateTimeField(
        verbose_name="Конец респа (UTC)",
    )
    location = models.CharField(
        max_length=100,
        blank=True,
        default="",
        verbose_name="Локация",
    )
    raw_data = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="Сырые данные (JSON)",
    )
    is_parsed_successfully = models.BooleanField(
        default=True,
        verbose_name="Успешно распарсен",
    )
    last_error = models.TextField(
        blank=True,
        default="",
        verbose_name="Последняя ошибка парсинга",
    )

    class Meta:
        verbose_name = "Респ РБ"
        verbose_name_plural = "Респы РБ"
        ordering = ["respawn_start"]

    def __str__(self) -> str:
        return f"{self.boss_name} ({self.boss_type})"


class BossRespawnSyncStatus(models.Model):
    """Статус синхронизации респа РБ (однозаписные, singleton pk=1)."""

    last_success_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Последний успех",
    )
    last_error_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Последняя ошибка",
    )
    last_attempt_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Последняя попытка",
    )
    last_error = models.TextField(
        blank=True,
        default="",
        verbose_name="Текст последней ошибки",
    )

    class Meta:
        verbose_name = "Статус синхронизации респов РБ"
        verbose_name_plural = "Статус синхронизации респов РБ"

    def __str__(self) -> str:
        return "Статус синхронизации респов РБ"


class EpicBossNotificationSettings(models.Model):
    """Настройки уведомлений об Эпик РБ (однозаписные, singleton pk=1)."""

    is_enabled = models.BooleanField(
        default=False,
        verbose_name="Уведомления включены",
    )
    notification_time = models.TimeField(
        default="18:00",
        verbose_name="Время отправки",
    )
    text_template = models.TextField(
        blank=True,
        default=DEFAULT_BOSS_TEMPLATE,
        verbose_name="Шаблон текста",
        help_text="Переменная {bosses} — список выбранных боссов с временем респа.",
    )
    selected_bosses = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Боссы для уведомлений",
        help_text="Имена боссов, по которым отправляются уведомления",
    )
    topic = models.ForeignKey(
        "TelegramTopic",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Тема в Telegram",
    )

    class Meta:
        verbose_name = "Настройка уведомлений Эпик РБ"
        verbose_name_plural = "Настройки уведомлений Эпик РБ"

    def __str__(self) -> str:
        return "Настройка уведомлений Эпик РБ"

    def clean(self) -> None:
        errors = {}
        if self.is_enabled and not self.text_template.strip():
            errors["text_template"] = (
                "Текст уведомления обязателен при включённых уведомлениях."
            )
        if errors:
            raise ValidationError(errors)
        if self.is_enabled and not self.selected_bosses:
            # Non-field ошибка: у ModelForm поле называется `bosses`, а не
            # `selected_bosses`, поэтому словарь с этим ключом ломал бы форму.
            raise ValidationError("Выбери хотя бы одного босса.")


class EpicBossNotificationLog(models.Model):
    """Журнал отправленных уведомлений об Эпик РБ (unique constrain на дату)."""

    notify_date = models.DateField(
        unique=True,
        verbose_name="Дата уведомления",
    )
    sent_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Время отправки",
    )
    bosses = models.JSONField(
        default=list,
        verbose_name="Боссы",
    )
    text = models.TextField(
        blank=True,
        default="",
        verbose_name="Текст",
    )
    success = models.BooleanField(
        default=True,
        verbose_name="Успешно",
    )

    class Meta:
        verbose_name = "Журнал уведомлений Эпик РБ"
        verbose_name_plural = "Журналы уведомлений Эпик РБ"
        ordering = ["-notify_date"]

    def __str__(self) -> str:
        return f"Уведомление Эпик РБ за {self.notify_date}"
