"""URL routes for the core module."""
from django.contrib.auth import views as auth_views
from django.urls import path

from core import views

urlpatterns = [
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="core/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("dashboard/", views.dashboard, name="dashboard_url"),
    path("players/", views.players, name="players"),
    path("players/toggle/<int:pk>/", views.toggle_player, name="player_toggle"),
    path("activities/", views.activities, name="activities"),
    path("telegram-messages/", views.telegram_messages, name="telegram_messages"),
    path("processing_errors/", views.processing_errors, name="processing_errors"),
    path("settings/", views.settings_view, name="settings"),
]
