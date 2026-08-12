"""Forms for the Smartline web interface."""
from datetime import datetime, time

from django import forms
from django.utils import timezone

from core.models import Player, Setting

_PERIOD_CHOICES = [
    ("today", "Сегодня"),
    ("week", "Неделя"),
    ("month", "Месяц"),
    ("custom", "Произвольный период"),
]

_TYPE_CHOICES = [
    ("", "Все"),
    ("DEF", "DEF"),
    ("FARM", "FARM"),
]


class PlayerForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["nickname"]
        widgets = {
            "nickname": forms.TextInput(attrs={"placeholder": "Игровой ник"}),
        }

    def clean_nickname(self) -> str:
        nickname = self.cleaned_data["nickname"].strip()
        if Player.objects.filter(nickname__iexact=nickname).exists():
            raise forms.ValidationError(
                f"Игрок с ником «{nickname}» уже существует (регистр не важен)."
            )
        return nickname


class ActivityFilterForm(forms.Form):
    player = forms.ModelChoiceField(
        queryset=Player.objects.order_by("nickname"),
        required=False,
        label="Игрок",
    )
    activity_type = forms.ChoiceField(
        choices=_TYPE_CHOICES,
        required=False,
        label="Тип",
    )
    date_from = forms.DateField(
        required=False,
        label="Дата с",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_to = forms.DateField(
        required=False,
        label="Дата по",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def apply_filters(self, queryset):
        data = self.cleaned_data if self.is_valid() else {}
        player = data.get("player")
        activity_type = data.get("activity_type")
        date_from = data.get("date_from")
        date_to = data.get("date_to")

        if player is not None:
            queryset = queryset.filter(player=player)
        if activity_type:
            queryset = queryset.filter(activity_type=activity_type)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)
        return queryset


class PeriodForm(forms.Form):
    period = forms.ChoiceField(
        choices=_PERIOD_CHOICES,
        required=False,
        initial="today",
        label="Период",
    )
    date_from = forms.DateField(
        required=False,
        label="Дата с",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    date_to = forms.DateField(
        required=False,
        label="Дата по",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    def clean(self) -> dict:
        cleaned = super().clean()
        period = cleaned.get("period") or "today"
        if period == "custom":
            date_from = cleaned.get("date_from")
            date_to = cleaned.get("date_to")
            if date_from and date_to and date_from > date_to:
                self.add_error("date_from", "Дата начала позже даты окончания")
        return cleaned

    def get_date_range(self):
        """Return an aware (date_from, date_to) range for the chosen period."""
        if self.is_valid():
            period = self.cleaned_data.get("period") or "today"
            date_from = self.cleaned_data.get("date_from")
            date_to = self.cleaned_data.get("date_to")
        else:
            period = "today"
            date_from = None
            date_to = None

        today = timezone.localdate()
        if period == "today":
            start = today
            end = today
        elif period == "week":
            start = today - timezone.timedelta(days=today.weekday())
            end = today
        elif period == "month":
            start = today.replace(day=1)
            end = today
        elif period == "custom":
            start = date_from or today
            end = date_to or today
        else:
            start = today
            end = today

        start_dt = timezone.make_aware(datetime.combine(start, time.min))
        end_dt = timezone.make_aware(datetime.combine(end, time.max))
        return start_dt, end_dt


class SettingForm(forms.ModelForm):
    class Meta:
        model = Setting
        fields = ["key", "value", "description"]
