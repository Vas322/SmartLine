"""Template filters for human-readable processing-error reasons."""
from django import template

from core.error_messages import friendly_error_message

register = template.Library()


@register.filter
def friendly_error(reason: str) -> str:
    """Return a user-facing Russian message for an internal error reason."""
    return friendly_error_message(reason)
