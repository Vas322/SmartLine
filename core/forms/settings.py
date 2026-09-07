"""Settings-related forms (welcome section)."""
from django import forms

from core.models import WelcomeSettings


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
