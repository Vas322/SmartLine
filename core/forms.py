"""Forms for the Smartline web interface."""
import re
from datetime import datetime, time

from django import forms
from django.db.models import Q
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from core.models import (
    CastRate,
    Instruction,
    Player,
    Rate,
    RegistrationRate,
    ScheduledMessage,
)

_WEEKDAY_CHOICES = [
    (0, "Пн"),
    (1, "Вт"),
    (2, "Ср"),
    (3, "Чт"),
    (4, "Пт"),
    (5, "Сб"),
    (6, "Вс"),
]

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
    ("CAST", "CAST"),
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
        if not re.fullmatch(r"^[A-Za-zА-Яа-яЁё0-9]+$", nickname):
            raise forms.ValidationError(
                "Ник может содержать только буквы русского/английского алфавита и цифры. Пожалуйста, исправьте игровой ник на корректный."
            )
        return nickname


class PlayerEditForm(forms.ModelForm):
    class Meta:
        model = Player
        fields = ["nickname", "telegram_user_id"]
        widgets = {
            "nickname": forms.TextInput(attrs={"placeholder": "Игровой ник"}),
            "telegram_user_id": forms.NumberInput(
                attrs={"placeholder": "Telegram user ID (необязательно)"}
            ),
        }
        labels = {
            "nickname": "Ник",
            "telegram_user_id": "Telegram user ID",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["telegram_user_id"].required = False

    def clean_nickname(self) -> str:
        nickname = self.cleaned_data["nickname"].strip()
        if not re.fullmatch(r"^[A-Za-zА-Яа-яЁё0-9]+$", nickname):
            raise forms.ValidationError(
                "Ник может содержать только буквы русского/английского алфавита и цифры. Пожалуйста, исправьте игровой ник на корректный."
            )
        existing = (
            Player.objects.filter(nickname__iexact=nickname)
            .exclude(pk=self.instance.pk)
            .exists()
        )
        if existing:
            raise forms.ValidationError(
                f"Игрок с ником «{nickname}» уже существует (регистр не важен)."
            )
        return nickname

    def clean_telegram_user_id(self):
        user_id = self.cleaned_data.get("telegram_user_id")
        if user_id is None:
            return None
        existing = (
            Player.objects.filter(telegram_user_id=user_id)
            .exclude(pk=self.instance.pk)
            .exists()
        )
        if existing:
            raise forms.ValidationError(
                "Этот Telegram user ID уже привязан к другому игроку."
            )
        return user_id


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
        else:
            period = self.initial.get("period") or "today"
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
            # Last day of the current calendar month.
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


class RateForm(forms.ModelForm):
    class Meta:
        model = Rate
        fields = ["start_time", "end_time", "rate_kk", "active", "order"]
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "end_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "rate_kk": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The add form on the settings page only posts time and rate fields;
        # active and order keep their model defaults when omitted.
        self.fields["active"].required = False
        self.fields["order"].required = False

    def clean_active(self) -> bool:
        return self.cleaned_data.get("active") or True

    def clean_order(self) -> int:
        return self.cleaned_data.get("order") or 0


class CastRateForm(forms.ModelForm):
    class Meta:
        model = CastRate
        fields = ["start_time", "end_time", "rate_kk", "active", "order"]
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "end_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "rate_kk": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The add form on the settings page only posts time and rate fields;
        # active and order keep their model defaults when omitted.
        self.fields["active"].required = False
        self.fields["order"].required = False

    def clean_active(self) -> bool:
        return self.cleaned_data.get("active") or True

    def clean_order(self) -> int:
        return self.cleaned_data.get("order") or 0


class RegistrationRateForm(forms.ModelForm):
    class Meta:
        model = RegistrationRate
        fields = ["start_time", "end_time", "rate_kk", "active", "order"]
        widgets = {
            "start_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "end_time": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "rate_kk": forms.NumberInput(attrs={"step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["active"].required = False
        self.fields["order"].required = False

    def clean_active(self) -> bool:
        return self.cleaned_data.get("active") or True

    def clean_order(self) -> int:
        return self.cleaned_data.get("order") or 0


class InstructionForm(forms.ModelForm):
    class Meta:
        model = Instruction
        fields = ["slug", "title", "content"]
        labels = {
            "slug": "Слаг",
            "title": "Заголовок",
            "content": "Содержание",
        }
        widgets = {
            "content": forms.Textarea(
                attrs={"class": "field-content auto-grow"}
            ),
        }


class SignUpForm(forms.Form):
    email = forms.EmailField(
        label="Email",
        max_length=254,
        widget=forms.EmailInput(attrs={"placeholder": "email@example.com"}),
    )
    username = forms.CharField(
        label="Имя пользователя",
        min_length=3,
        max_length=150,
        widget=forms.TextInput(attrs={"placeholder": "username"}),
    )
    password = forms.CharField(
        label="Пароль",
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Пароль"}),
    )
    password_confirm = forms.CharField(
        label="Подтверждение пароля",
        strip=False,
        widget=forms.PasswordInput(attrs={"placeholder": "Повторите пароль"}),
    )

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Пользователь с таким email уже существует.")
        return email

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Пользователь с таким именем уже существует.")
        return username

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        password_confirm = cleaned.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Пароли не совпадают.")
        if password:
            try:
                validate_password(password)
            except ValidationError as e:
                self.add_error("password", list(e.messages))
        return cleaned


class CustomDatesWidget(forms.Widget):
    """Виджет набора дат: несколько DateInput (type=date) + кнопки добавить/удалить.

    Хранит значение как список строк "YYYY-MM-DD". Имена полей ввода —
    ``<name>_<index>``, что позволяет динамически добавлять/удалять строки
    на клиенте без фиксированного количества полей.
    """

    template_name = "admin/widgets/custom_dates.html"

    def __init__(self, attrs=None):
        default_attrs = {"type": "date", "class": "vDateField"}
        if attrs:
            default_attrs.update(attrs)
        super().__init__(attrs=default_attrs)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        dates = value if value else []
        if not dates:
            dates = [""]
        context["widget"]["dates"] = list(dates)
        return context

    def value_from_datadict(self, data, files, name):
        """Собрать все даты из полей <name>_<index> в список строк."""
        dates = []
        index = 0
        while True:
            key = f"{name}_{index}"
            if key not in data:
                break
            value = data.get(key)
            if value:
                dates.append(value)
            index += 1
        return dates


class CustomDatesField(forms.Field):
    """Поле набора конкретных дат, преобразует в JSON-список строк."""

    widget = CustomDatesWidget

    def to_python(self, value):
        dates = []
        for item in value or []:
            item = (item or "").strip()
            if not item:
                continue
            try:
                datetime.strptime(item, "%Y-%m-%d")
            except ValueError:
                raise forms.ValidationError(
                    f"Дата «{item}» указана в неверном формате."
                )
            dates.append(item)
        return dates


class WeekdayCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """CheckboxSelectMultiple, рендерящийся горизонтальным рядом дней недели."""

    template_name = "admin/widgets/weekday_checkboxes.html"


class ScheduledMessageAdminForm(forms.ModelForm):
    """Форма админки для сообщений по расписанию."""

    weekdays = forms.TypedMultipleChoiceField(
        choices=_WEEKDAY_CHOICES,
        coerce=int,
        widget=WeekdayCheckboxSelectMultiple,
        label="Дни недели",
        required=False,
        help_text="Для «Ежемесячно» и «Произвольных дат» не требуется.",
    )
    custom_dates = CustomDatesField(
        required=False,
        label="Конкретные даты",
        help_text="Даты в формате ГГГГ-ММ-ДД.",
    )

    class Meta:
        model = ScheduledMessage
        fields = [
            "name",
            "text",
            "topic",
            "weekdays",
            "time",
            "frequency",
            "start_date",
            "end_date",
            "custom_dates",
            "is_active",
        ]
        help_texts = {
            "end_date": (
                "Оставьте пустым — сообщение будет отправляться бессрочно "
                "(пока активно)."
            ),
        }

    def clean(self):
        cleaned = super().clean()
        frequency = cleaned.get("frequency")
        weekdays = cleaned.get("weekdays") or []
        if (
            frequency in (ScheduledMessage.Frequency.WEEKLY, ScheduledMessage.Frequency.BIWEEKLY)
            and not weekdays
        ):
            self.add_error("weekdays", "Укажите хотя бы один день недели.")
        return cleaned
