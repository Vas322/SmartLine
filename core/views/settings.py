"""Settings views."""
import logging

from django.shortcuts import redirect, render

from core.decorators import staff_or_404
from core.forms import CastRateForm, RateForm, RegistrationRateForm
from core.models import CastRate, Rate, RegistrationRate


logger = logging.getLogger(__name__)


def _delete_rate(request, post_key: str, model) -> bool:
    """Handle a delete POST for a rate model. Returns True if redirect needed."""
    pk = request.POST.get(post_key)
    if not pk:
        return False
    try:
        model.objects.filter(pk=pk).delete()
    except (TypeError, ValueError):
        pass
    return True


def _process_rate_form(request, prefix: str, form_class, model):
    """Handle add/edit POST for one rate kind.

    Returns (handled, open_flag, form):
    - handled: True when this kind's add/edit was submitted in POST.
    - open_flag: useful only when handled; True means the add/edit form is open.
    - form: None when a redirect already happened (successful save); otherwise
      the bound form (possibly invalid) or an empty form when the edit target
      was not found.
    """
    add_key = f"add_{prefix}rate"
    edit_key = f"edit_{prefix}rate"

    if not (request.POST.get(add_key) or request.POST.get(edit_key)):
        return False, False, None

    if request.POST.get(edit_key):
        instance = model.objects.filter(pk=request.POST[edit_key]).first()
        if instance:
            form = form_class(request.POST, instance=instance)
            if form.is_valid():
                form.save()
                return True, True, None
        else:
            form = form_class()
    else:
        form = form_class(request.POST)
        if form.is_valid():
            form.save()
            return True, True, None

    return True, True, form


@staff_or_404
def settings_view(request):
    edit_rate_pk = request.GET.get("edit") or request.POST.get("edit_rate")
    edit_cast_rate_pk = request.GET.get("edit_cast") or request.POST.get("edit_cast_rate")
    edit_reg_rate_pk = request.GET.get("edit_reg") or request.POST.get("edit_reg_rate")

    def_add_open = False
    cast_add_open = False
    reg_add_open = False

    rate_form = None
    cast_rate_form = None
    reg_rate_form = None

    if request.method == "POST":
        if _delete_rate(request, "delete_rate", Rate):
            return redirect("settings")
        if _delete_rate(request, "delete_cast_rate", CastRate):
            return redirect("settings")
        if _delete_rate(request, "delete_reg_rate", RegistrationRate):
            return redirect("settings")

        handled, def_add_open, rate_form = _process_rate_form(request, "", RateForm, Rate)
        if not handled:
            handled, cast_add_open, cast_rate_form = _process_rate_form(
                request, "cast_", CastRateForm, CastRate
            )
        if not handled:
            handled, reg_add_open, reg_rate_form = _process_rate_form(
                request, "reg_", RegistrationRateForm, RegistrationRate
            )

        if rate_form is None and def_add_open:
            return redirect("settings")
        if cast_rate_form is None and cast_add_open:
            return redirect("settings")
        if reg_rate_form is None and reg_add_open:
            return redirect("settings")

    if rate_form is None:
        rate = Rate.objects.filter(pk=edit_rate_pk).first() if edit_rate_pk else None
        rate_form = RateForm(instance=rate) if rate else RateForm()
    if cast_rate_form is None:
        cast_rate = (
            CastRate.objects.filter(pk=edit_cast_rate_pk).first()
            if edit_cast_rate_pk
            else None
        )
        cast_rate_form = CastRateForm(instance=cast_rate) if cast_rate else CastRateForm()
    if reg_rate_form is None:
        reg_rate = (
            RegistrationRate.objects.filter(pk=edit_reg_rate_pk).first()
            if edit_reg_rate_pk
            else None
        )
        reg_rate_form = RegistrationRateForm(instance=reg_rate) if reg_rate else RegistrationRateForm()

    rates = Rate.objects.all()
    cast_rates = CastRate.objects.all()
    reg_rates = RegistrationRate.objects.all()
    return render(
        request,
        "core/settings.html",
        {
            "rate_form": rate_form,
            "rates": rates,
            "edit_rate_pk": edit_rate_pk,
            "def_add_open": def_add_open,
            "cast_rate_form": cast_rate_form,
            "cast_rates": cast_rates,
            "edit_cast_rate_pk": edit_cast_rate_pk,
            "cast_add_open": cast_add_open,
            "reg_rate_form": reg_rate_form,
            "reg_rates": reg_rates,
            "edit_reg_rate_pk": edit_reg_rate_pk,
            "reg_add_open": reg_add_open,
        },
    )
