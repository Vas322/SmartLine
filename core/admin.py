"""Django admin registration for the core models."""
from django.contrib import admin

from core.models import Activity, Player, ProcessingError, Setting, TelegramMessage


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = (
        "nickname",
        "telegram_user_id",
        "telegram_username",
        "is_active",
        "created_at",
        "updated_at",
    )
    search_fields = ("nickname", "telegram_username")
    list_filter = ("is_active",)


@admin.register(TelegramMessage)
class TelegramMessageAdmin(admin.ModelAdmin):
    list_display = ("telegram_chat_id", "telegram_message_id", "status", "created_at")
    search_fields = ("telegram_chat_id", "telegram_message_id", "text")


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("player", "activity_type", "amount", "created_at")
    list_filter = ("activity_type",)
    search_fields = ("player__nickname",)


@admin.register(ProcessingError)
class ProcessingErrorAdmin(admin.ModelAdmin):
    list_display = ("reason", "status", "created_at")
    list_filter = ("status",)


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "description")
    search_fields = ("key",)
