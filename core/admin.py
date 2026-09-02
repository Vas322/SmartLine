"""Django admin registration for the core models."""
from django.contrib import admin, messages

from core.models import Activity, CastRate, OutgoingMessage, Player, ProcessingError, Registration, RegistrationRate, ScheduleMirror, TelegramMessage, TelegramSettings, TelegramTopic
from core.services import schedule_mirror_service


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


@admin.register(OutgoingMessage)
class OutgoingMessageAdmin(admin.ModelAdmin):
    list_display = (
        "sent_at",
        "sent_by",
        "text_snippet",
        "topic_name",
        "status",
    )
    search_fields = ("text", "reply_to_text")
    list_filter = ("status",)

    def text_snippet(self, obj):
        return (obj.text or "")[:60]
    text_snippet.short_description = "Текст"


class TelegramTopicInline(admin.TabularInline):
    model = TelegramTopic
    fk_name = "group"
    extra = 0

    def has_add_permission(self, request, obj=None):
        return request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff


@admin.register(TelegramSettings)
class TelegramSettingsAdmin(admin.ModelAdmin):
    """Группы Telegram с инлайновыми темами."""

    list_display = ("name", "group_chat_id", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "group_chat_id")
    fields = ("name", "group_chat_id", "is_active")
    inlines = [TelegramTopicInline]

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return request.user.is_staff

    def has_delete_permission(self, request, obj=None):
        return request.user.is_staff


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ("player", "type_display", "amount", "created_at")
    list_filter = ("activity_type",)
    search_fields = ("player__nickname",)


@admin.register(CastRate)
class CastRateAdmin(admin.ModelAdmin):
    list_display = ("start_time", "end_time", "rate_kk", "active", "order")
    list_filter = ("active",)


@admin.register(RegistrationRate)
class RegistrationRateAdmin(admin.ModelAdmin):
    list_display = ("start_time", "end_time", "rate_kk", "active", "order")
    list_filter = ("active",)


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ("player", "clans_count", "payment_kk", "registered_at")
    list_filter = ("player",)
    search_fields = ("player__nickname",)


@admin.register(ProcessingError)
class ProcessingErrorAdmin(admin.ModelAdmin):
    list_display = ("reason", "status", "created_at")
    list_filter = ("status",)


@admin.register(ScheduleMirror)
class ScheduleMirrorAdmin(admin.ModelAdmin):
    list_display = (
        "source_chat_id",
        "source_message_id",
        "target_chat_id",
        "target_message_id",
        "alliance_bot_username",
        "label",
        "is_active",
        "last_synced_at",
    )
    list_filter = ("is_active",)
    search_fields = ("alliance_bot_username", "label", "source_chat_id", "target_chat_id")
    readonly_fields = ("last_synced_at", "created_at", "updated_at", "created_by")
    actions = ["action_refresh_schedule", "action_publish_schedule"]
    change_form_template = "admin/core/schedulemirror/change_form.html"

    @admin.action(description="Обновить расписание (показать последний текст из канала)")
    def action_refresh_schedule(self, request, queryset):
        for mirror in queryset:
            text = schedule_mirror_service.get_schedule_text(mirror_id=mirror.id)
            if text:
                self.message_user(
                    request,
                    f"Зеркало #{mirror.id}: загружен сохранённый текст расписания ({len(text)} симв.).",
                    level=messages.INFO,
                )
            else:
                self.message_user(
                    request,
                    f"Зеркало #{mirror.id}: текст пуст. Вставьте вручную или дождитесь поста бота.",
                    level=messages.WARNING,
                )

    @admin.action(description="Отправить текущее расписание в целевую группу (новым сообщением)")
    def action_publish_schedule(self, request, queryset):
        for mirror in queryset:
            try:
                schedule_mirror_service.publish_current_text(mirror_id=mirror.id, user=request.user)
                self.message_user(
                    request,
                    f"Зеркало #{mirror.id}: расписание отправлено в группу новым сообщением.",
                    level=messages.SUCCESS,
                )
            except Exception as exc:
                self.message_user(
                    request,
                    f"Зеркало #{mirror.id}: ошибка отправки — {exc}",
                    level=messages.ERROR,
                )
