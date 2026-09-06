"""Core data models — Part 5: instruction and schedule mirror models."""
from django.conf import settings
from django.db import models


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