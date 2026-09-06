"""Scheduled message admin forms and widgets."""
from datetime import datetime

from django import forms

from core.models import ScheduledMessage

_WEEKDAY_CHOICES = [
    (0, "Пн"),
    (1, "Вт"),
    (2, "Ср"),
    (3, "Чт"),
    (4, "Пт"),
    (5, "Сб"),
    (6, "Вс"),
]


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