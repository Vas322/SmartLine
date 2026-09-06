"""Authentication and user profile views."""
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from core.forms import SignUpForm
from core.views.common import MEMBERS_GROUP


logger = logging.getLogger(__name__)


def _send_activation_email(request, user):
    """Send email with activation link."""
    token = default_token_generator.make_token(user)
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    activation_path = reverse("activate", kwargs={"uidb64": uid, "token": token})
    activation_url = request.build_absolute_uri(activation_path)
    subject = "Smartline — Подтверждение регистрации"
    message = (
        f"Здравствуйте, {user.username}!\n\n"
        f"Для завершения регистрации перейдите по ссылке:\n"
        f"{activation_url}\n\n"
        f"Ссылка действительна в течение 48 часов.\n\n"
        f"Если вы не регистрировались в Smartline — игнорируйте это письмо."
    )
    send_mail(subject, message, None, [user.email])


def signup_view(request):
    """User registration with email verification."""
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                is_active=False,
            )
            _send_activation_email(request, user)
            logger.info("Registration: user %s created, activation email sent", user.username)
            return redirect("activation_sent")
    else:
        form = SignUpForm()
    return render(request, "core/signup.html", {"form": form})


def activate_view(request, uidb64, token):
    """Activate user account from email link."""
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()
        members_group, _ = Group.objects.get_or_create(name=MEMBERS_GROUP)
        user.groups.add(members_group)
        logger.info("Activation: user %s activated", user.username)
        return render(request, "core/activation_complete.html")

    logger.warning("Activation failed: invalid token or user")
    return render(request, "core/activation_invalid.html")


def activation_sent_view(request):
    """Show 'check your email' message."""
    return render(request, "core/activation_sent.html")


@login_required
def profile_view(request):
    """User profile page."""
    return render(request, "core/profile.html")