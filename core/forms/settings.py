"""Settings-related forms (welcome + epic boss notifications)."""
from django import forms

from core.models import (
    BossRespawn,
    EpicBossNotificationSettings,
    TelegramTopic,
    WelcomeSettings,
)


class WelcomeSettingsForm(forms.ModelForm):
    class Meta:
        model = WelcomeSettings
        fields = ["welcome_text"]
        widgets = {
            "welcome_text": forms.Textarea(
                attrs={"rows": 4, "placeholder": "Текст приветствия"}
            ),
        }
        labels = {
            "welcome_text": "Текст приветствия",
        }


def _boss_choices() -> list:
    """Список боссов из БД, сгруппированный по типу (Эпик / Сабкласс)."""
    bosses = BossRespawn.objects.order_by("boss_type", "respawn_start")
    epic = [
        (b.boss_name, b.boss_name)
        for b in bosses
        if b.boss_type == BossRespawn.BossType.EPIC
    ]
    subclass = [
        (b.boss_name, b.boss_name)
        for b in bosses
        if b.boss_type == BossRespawn.BossType.SUBCLASS
    ]
    groups = []
    if epic:
        groups.append(("Эпик", epic))
    if subclass:
        groups.append(("Сабкласс", subclass))
    return groups


class EpicBossNotificationSettingsForm(forms.ModelForm):
    notification_time = forms.TimeField(
        required=True,
        widget=forms.TimeInput(format="%H:%M", attrs={"type": "time"}),
        label="Время отправки (МСК)",
    )
    bosses = forms.MultipleChoiceField(
        required=False,
        choices=_boss_choices,
        widget=forms.CheckboxSelectMultiple,
        label="Боссы для уведомлений",
    )

    class Meta:
        model = EpicBossNotificationSettings
        fields = ["is_enabled", "notification_time", "topic", "text_template", "bosses"]
        widgets = {
            "text_template": forms.Textarea(
                attrs={
                    "rows": 6,
                    "placeholder": "🎮 Сегодня респ Эпик РБ\n\nБоссы:\n{bosses}\n\nОкно респа: ~24 часа.",
                }
            ),
        }
        labels = {
            "is_enabled": "Уведомления включены",
            "text_template": "Текст уведомления",
            "topic": "Тема в Telegram",
        }
        help_texts = {
            "text_template": (
                "Вместо {bosses} подставится список выбранных боссов с временем респа."
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Показываем только активные темы активной группы.
        self.fields["topic"].queryset = TelegramTopic.objects.filter(
            group__is_active=True,
            is_active=True,
        )
        # Текущие сохранённые боссы — выбранными по умолчанию.
        if self.instance and self.instance.pk:
            self.fields["bosses"].initial = list(self.instance.selected_bosses or [])

    def clean_bosses(self) -> list:
        selected = self.cleaned_data.get("bosses") or []
        valid_names = set(
            BossRespawn.objects.filter(boss_name__in=selected).values_list(
                "boss_name", flat=True
            )
        )
        return [name for name in selected if name in valid_names]

    def clean(self):
        cleaned = super().clean()
        is_enabled = cleaned.get("is_enabled")
        bosses = cleaned.get("bosses") or []
        # Синхронизируем выбранных боссов с инстансом до полной валидации модели,
        # чтобы model.clean() видел актуальный список.
        self.instance.selected_bosses = list(bosses)
        if is_enabled and not bosses:
            self.add_error(
                "bosses", "Выбери хотя бы одного босса."
            )
        return cleaned

    def save(self, commit=True) -> EpicBossNotificationSettings:
        instance = super().save(commit=False)
        instance.selected_bosses = list(self.cleaned_data.get("bosses") or [])
        if commit:
            instance.save()
        return instance

