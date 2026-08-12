"""URL routes for reports and exports."""
from django.urls import path

from reports import views

urlpatterns = [
    path("export/", views.export_activities, name="export_excel"),
]