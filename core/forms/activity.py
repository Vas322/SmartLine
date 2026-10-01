"""Activity filter and period forms."""
from datetime import datetime, time

from django import forms
from django.db.models import Q
from django.utils import timezone

from core.models import Player

_PERIOD_CHOICES = [
    ("today", "Сегодня"),
    ("week", "Неделя"),
    ("month", "Месяц"),
    ("custom", "Произвольный период"),
]

_MONTH_NAMES = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]


def _months_ago(ref, count):
    """Return (year, month) tuple `count` months before `ref` (a date)."""
    month = ref.month - count
    year = ref.year
    while month <= 0:
        month += 12
        year -= 1
    return year, month


def get_month_choices():
    """Last 13 calendar months including the current one, as (YYYY-MM, label)."""
    now = timezone.localdate()
    return [
        (
            f"{year:04d}-{month:02d}",
            f"{_MONTH_NAMES[month - 1].capitalize()} {year}",
        )
        for year, month in (_months_ago(now, i) for i in range(12, -1, -1))
    ]


_TYPE_CHOICES = [
    ("", "Все"),
    ("DEF", "DEF"),
    ("FARM", "FARM"),
    ("CAST", "CAST"),
]


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
            if activity_type == "CAST":
                queryset = queryset.filter(Q(activity_type="CAST") | Q(has_cast=True))
            else:
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
        widget=forms.Select(attrs={"class": "period-select"}),
    )
    date_from = forms.DateField(
        required=False,
        label="Дата с",
        widget=forms.DateInput(
            attrs={"type": "date", "class": "period-date"}
        ),
    )
    date_to = forms.DateField(
        required=False,
        label="Дата по",
        widget=forms.DateInput(
            attrs={"type": "date", "class": "period-date"}
        ),
    )
    month = forms.ChoiceField(
        choices=get_month_choices,
        required=False,
        label="Месяц",
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

    def _get_period_dates(self):
        """Return (start_date, end_date) as date objects for the chosen period."""
        if self.is_valid():
            period = self.cleaned_data.get("period") or self.initial.get("period") or "today"
            date_from = self.cleaned_data.get("date_from")
            date_to = self.cleaned_data.get("date_to")
            month = self.cleaned_data.get("month")
        else:
            period = self.initial.get("period") or "today"
            date_from = None
            date_to = None
            month = self.initial.get("month")

        today = timezone.localdate()
        if period == "today":
            start = today
            end = today
        elif period == "week":
            start = today - timezone.timedelta(days=today.weekday())
            end = today
        elif period == "month":
            start = today.replace(day=1)
            if month:
                try:
                    start = datetime.strptime(month, "%Y-%m").date()
                except (ValueError, TypeError):
                    pass
            # Last day of the selected calendar month.
            next_month = start.replace(day=28) + timezone.timedelta(days=4)
            end = next_month.replace(day=1) - timezone.timedelta(days=1)
        elif period == "custom":
            start = date_from or today
            end = date_to or today
        else:
            start = today
            end = today

        return start, end

    def get_date_range(self):
        """Return an aware (date_from, date_to) range for the chosen period."""
        start, end = self._get_period_dates()
        start_dt = timezone.make_aware(datetime.combine(start, time.min))
        end_dt = timezone.make_aware(datetime.combine(end, time.max))
        return start_dt, end_dt

    def get_days_in_period(self) -> int:
        """Return the number of days in the chosen period."""
        start, end = self._get_period_dates()
        return (end - start).days + 1
