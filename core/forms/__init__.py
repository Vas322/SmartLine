"""Forms package — re-exports all forms, widgets and fields from submodules."""
from core.forms.activity import ActivityFilterForm, PeriodForm
from core.forms.auth import SignUpForm
from core.forms.instructions import InstructionForm
from core.forms.players import PlayerEditForm, PlayerForm
from core.forms.rates import CastRateForm, RateForm, RegistrationRateForm
from core.forms.scheduled_messages import (
    CustomDatesField,
    CustomDatesWidget,
    ScheduledMessageAdminForm,
    WeekdayCheckboxSelectMultiple,
)

__all__ = [
    "PlayerForm",
    "PlayerEditForm",
    "ActivityFilterForm",
    "PeriodForm",
    "RateForm",
    "CastRateForm",
    "RegistrationRateForm",
    "InstructionForm",
    "SignUpForm",
    "CustomDatesField",
    "CustomDatesWidget",
    "WeekdayCheckboxSelectMultiple",
    "ScheduledMessageAdminForm",
]
