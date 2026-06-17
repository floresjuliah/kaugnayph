from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Allows {{ mydict|get_item:somekey }} in templates for dict lookups by variable key."""
    if dictionary is None:
        return None
    return dictionary.get(key)