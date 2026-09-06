"""Instruction forms."""
from django import forms

from core.models import Instruction


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
