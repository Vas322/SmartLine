"""Simple math template filters used by templates (e.g. summary note)."""
from django import template

register = template.Library()


@register.filter
def sub(value, arg):
    """Subtract arg from value; on failure return the original value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value
