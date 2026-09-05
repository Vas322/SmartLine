"""URL routes for the core module."""
from django.contrib.auth import views as auth_views
from django.urls import path

from core import views

urlpatterns = [
    # Auth
    path("register/", views.signup_view, name="signup"),
    path("activate/<str:uidb64>/<str:token>/", views.activate_view, name="activate"),
    path("activation-sent/", views.activation_sent_view, name="activation_sent"),
    path("profile/", views.profile_view, name="profile"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="core/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Password reset
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="core/password_reset.html",
            email_template_name="core/password_reset_email.html",
            subject_template_name="core/password_reset_subject.txt",
            success_url="/password-reset/done/",
        ),
        name="password_reset",
    ),
    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="core/password_reset_done.html",
        ),
        name="password_reset_done",
    ),
    path(
        "password-reset/<str:uidb64>/<str:token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="core/password_reset_confirm.html",
            success_url="/password-reset/complete/",
        ),
        name="password_reset_confirm",
    ),
    path(
        "password-reset/complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="core/password_reset_complete.html",
        ),
        name="password_reset_complete",
    ),
    # App
    path("", views.dashboard, name="dashboard"),
    path("dashboard/", views.dashboard, name="dashboard_url"),
    path("players/", views.players, name="players"),
    path("player/<int:pk>/", views.player_detail, name="player_detail"),
    path("players/toggle/<int:pk>/", views.toggle_player, name="player_toggle"),
    path("players/delete/<int:pk>/", views.delete_player, name="player_delete"),
    path("players/edit/<int:pk>/", views.player_edit, name="player_edit"),
    path("activities/", views.activities, name="activities"),
    path("telegram-messages/", views.telegram_messages, name="telegram_messages"),
    path(
        "telegram-messages/send-reply/",
        views.send_reply,
        name="send_reply",
    ),
    path(
        "telegram-messages/send-message/",
        views.send_message,
        name="send_message",
    ),
    path("instructions/", views.instructions, name="instructions"),
    path(
        "instructions/<int:pk>/",
        views.instruction_detail,
        name="instruction_detail",
    ),
    path(
        "instructions/<int:pk>/edit/",
        views.instruction_edit,
        name="instruction_edit",
    ),
    path("settings/", views.settings_view, name="settings"),
    path("schedule/", views.schedule_mirror, name="schedule_mirror"),
]
