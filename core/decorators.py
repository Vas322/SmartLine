"""Custom decorators for access control."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login


def member_required(view_func):
    """Allow access to authenticated users who are staff or Members group."""
    @wraps(view_func)
    @login_required
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if user.is_active and (user.is_staff or user.groups.filter(name="Members").exists()):
            return view_func(request, *args, **kwargs)
        return redirect_to_login(request.get_full_path())
    return _wrapped
