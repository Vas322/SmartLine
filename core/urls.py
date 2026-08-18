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
    path("player/<int:pk>/", views.player_detail, name="player_detail"),
    path("players/toggle/<int:pk>/", views.toggle_player, name="player_toggle"),
    path("players/delete/<int:pk>/", views.delete_player, name="player_delete"),
    path("activities/", views.activities, name="activities"),
    path("telegram-messages/", views.telegram_messages, name="telegram_messages"),
    path("processing_errors/", views.processing_errors, name="processing_errors"),
    path("instructions/", views.instructions, name="instructions"),
    path(
        "instructions/<int:pk>/",
        views.instruction_edit,
        name="instruction_edit",
    ),
    path("settings/", views.settings_view, name="settings"),
]
