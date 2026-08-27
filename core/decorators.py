"""Custom decorators for access control."""
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def member_required(view_func):
    """Allow access to authenticated users who are staff or Members group."""
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        if request.user.is_staff or request.user.groups.filter(name="Members").exists():
            return view_func(request, *args, **kwargs)
        return redirect(settings.LOGIN_URL)
    return _wrapped