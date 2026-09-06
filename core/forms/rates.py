"""Rate forms."""
from django import forms

from core.models import CastRate, Rate, RegistrationRate


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
