"""Web views for reports and exports."""
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.http import HttpResponse

from core.forms import PeriodForm
from reports.services.excel_exporter import export_activities_excel

_EXCEL_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)


@login_required
@require_GET
def export_activities(request) -> HttpResponse:
    """Return activities for the selected period as an XLSX file."""
    form = PeriodForm(request.GET or None)
    date_from, date_to = form.get_date_range()

    stream = export_activities_excel(date_from, date_to)
    response = HttpResponse(
        stream.getvalue(),
        content_type=_EXCEL_CONTENT_TYPE,
    )
    response["Content-Disposition"] = 'attachment; filename="activities.xlsx"'
    return response