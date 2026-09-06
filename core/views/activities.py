"""Activity listing views."""
import logging

from django.shortcuts import render

from core.decorators import staff_or_404
from core.forms import ActivityFilterForm
from core.models import Activity


logger = logging.getLogger(__name__)


@staff_or_404
def activities(request):
    form = ActivityFilterForm(request.GET or None)
    activities_qs = (
        Activity.objects.select_related("player", "telegram_message")
        .order_by("-created_at")
    )
    activities_qs = form.apply_filters(activities_qs)
    return render(
        request,
        "core/activities.html",
        {"activities": activities_qs, "form": form},
    )
