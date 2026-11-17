"""Template helpers for the AVELLE design system.

    {% load avelle_ui %}
    {% icon "search" %}
    {% icon "chevron-down" "icon--sm" %}
    {{ product.price|naira }}
"""
from decimal import Decimal, InvalidOperation

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html

from apps.core.utils import cloudinary_optimised

register = template.Library()


@register.simple_tag
def icon(name, css_class=""):
    """Inline reference to an icon in the static SVG sprite (static/img/icons.svg)."""
    return format_html(
        '<svg class="icon {}" aria-hidden="true" focusable="false"><use href="{}#i-{}"></use></svg>',
        css_class,
        static("img/icons.svg"),
        name,
    )


@register.filter
def naira(value):
    """Format a number as currency: 12500 -> ₦12,500 ; 12500.5 -> ₦12,500.50"""
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value
    symbol = getattr(settings, "CURRENCY_SYMBOL", "₦")
    if amount == amount.to_integral_value():
        return f"{symbol}{amount:,.0f}"
    return f"{symbol}{amount:,.2f}"


@register.filter
def cdn(url, width=800):
    """{{ image.url|cdn:640 }} -> Cloudinary URL with automatic format/quality and a width cap."""
    try:
        return cloudinary_optimised(url, int(width))
    except (TypeError, ValueError):
        return url
