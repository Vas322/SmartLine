"""Data models for the Smartline core module."""
from django.conf import settings
from django.db import models


class Player(models.Model):
    nickname = models.CharField(max_length=64, unique=True)
    telegram_user_id = models.BigIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["telegram_user_id"],
                condition=models.Q(telegram_user_id__isnull=False),
                name="uniq_player_telegram_user_id",
            )
        ]

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


class Activity(models.Model):
    class ActivityType(models.TextChoices):
        DEF = "DEF", "DEF"
        FARM = "FARM", "FARM"
        CAST = "CAST", "CAST"

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


class Registration(models.Model):
    """Регистрация клана на атаку форта."""
    player = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name="registrations",
    )
    telegram_message = models.OneToOneField(
        TelegramMessage,
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


class ScheduleMirror(models.Model):
    source_chat_id = models.BigIntegerField(
        verbose_name="ID исходного чата (мостовая группа)",
        help_text="Группа/канал, где бот альянса публикует расписание.",
    )
    source_message_id = models.BigIntegerField(
        verbose_name="ID сообщения с расписанием",
        help_text="ID сообщения от бота альянса (узнать через @getidsbot или в логах).",
    )
    target_chat_id = models.BigIntegerField(
        verbose_name="ID целевого чата (группа клана)",
        help_text="Группа клана, куда зеркалируется расписание.",
    )
    target_message_id = models.BigIntegerField(
        verbose_name="ID сообщения в целевой группе",
        help_text="Сообщение, которое бот обновляет при синхронизации.",
    )
    alliance_bot_username = models.CharField(
        max_length=64,
        blank=True,
        default="",
        verbose_name="Username бота альянса",
        help_text="Без @, например: x5_fort_bot.",
    )
    label = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="Название / метка",
        help_text="Необязательная метка для удобства (например: «Расписание на неделю»).",
    )
    last_text = models.TextField(
        default="",
        verbose_name="Последний текст расписания",
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="Последняя синхронизация",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Активно",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_schedule_mirrors",
        verbose_name="Кем создано",
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
        ordering = ["-created_at"]
        verbose_name = "Расписание"
        verbose_name_plural = "Расписания"
        constraints = [
            models.UniqueConstraint(
                fields=["source_chat_id", "source_message_id"],
                name="uniq_schedule_mirror_source",
            ),
        ]

    def __str__(self) -> str:
        return f"ScheduleMirror(src={self.source_chat_id}:{self.source_message_id}, active={self.is_active})"
