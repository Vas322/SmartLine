"""Django admin registration for the core models."""
from django.contrib import admin

from core.models import Activity, CastRate, Player, ProcessingError, TelegramMessage


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = (
        "nickname",
        "is_active",
        "created_at",
        "updated_at",
    )
    search_fields = ("nickname",)
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


@admin.register(CastRate)
class CastRateAdmin(admin.ModelAdmin):
    list_display = ("start_time", "end_time", "rate_kk", "active", "order")
    list_filter = ("active",)


@admin.register(ProcessingError)
class ProcessingErrorAdmin(admin.ModelAdmin):
    list_display = ("reason", "status", "created_at")
    list_filter = ("status",)
