"""Settings views."""
import logging

from django.shortcuts import redirect, render

from core.decorators import staff_or_404
from core.forms import CastRateForm, RateForm, RegistrationRateForm
from core.models import CastRate, Rate, RegistrationRate


logger = logging.getLogger(__name__)


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
        rate_pk = request.POST.get("delete_rate")
        if rate_pk:
            try:
                Rate.objects.filter(pk=rate_pk).delete()
            except (TypeError, ValueError):
                pass
            return redirect("settings")

        cast_rate_pk = request.POST.get("delete_cast_rate")
        if cast_rate_pk:
            try:
                CastRate.objects.filter(pk=cast_rate_pk).delete()
            except (TypeError, ValueError):
                pass
            return redirect("settings")

        reg_rate_pk = request.POST.get("delete_reg_rate")
        if reg_rate_pk:
            try:
                RegistrationRate.objects.filter(pk=reg_rate_pk).delete()
            except (TypeError, ValueError):
                pass
            return redirect("settings")

        if request.POST.get("add_rate") or request.POST.get("edit_rate"):
            def_add_open = True
            if request.POST.get("edit_rate"):
                rate = Rate.objects.filter(pk=request.POST["edit_rate"]).first()
                if rate:
                    rate_form = RateForm(request.POST, instance=rate)
                    if rate_form.is_valid():
                        rate_form.save()
                        return redirect("settings")
                else:
                    rate_form = RateForm()
            else:
                rate_form = RateForm(request.POST)
                if rate_form.is_valid():
                    rate_form.save()
                    return redirect("settings")
        elif request.POST.get("add_cast_rate") or request.POST.get("edit_cast_rate"):
            cast_add_open = True
            if request.POST.get("edit_cast_rate"):
                cast_rate = CastRate.objects.filter(pk=request.POST["edit_cast_rate"]).first()
                if cast_rate:
                    cast_rate_form = CastRateForm(request.POST, instance=cast_rate)
                    if cast_rate_form.is_valid():
                        cast_rate_form.save()
                        return redirect("settings")
                else:
                    cast_rate_form = CastRateForm()
            else:
                cast_rate_form = CastRateForm(request.POST)
                if cast_rate_form.is_valid():
                    cast_rate_form.save()
                    return redirect("settings")
        elif request.POST.get("add_reg_rate") or request.POST.get("edit_reg_rate"):
            reg_add_open = True
            if request.POST.get("edit_reg_rate"):
                reg_rate = RegistrationRate.objects.filter(pk=request.POST["edit_reg_rate"]).first()
                if reg_rate:
                    reg_rate_form = RegistrationRateForm(request.POST, instance=reg_rate)
                    if reg_rate_form.is_valid():
                        reg_rate_form.save()
                        return redirect("settings")
                else:
                    reg_rate_form = RegistrationRateForm()
            else:
                reg_rate_form = RegistrationRateForm(request.POST)
                if reg_rate_form.is_valid():
                    reg_rate_form.save()
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