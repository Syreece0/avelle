"""Small colour helpers for the lookbook hero (WCAG relative luminance, no dependencies)."""
import re

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def hex_to_rgb(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _channel(c):
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(value):
    r, g, b = (_channel(c) for c in hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


DARK_INK = "#171717"
LIGHT_INK = "#FAF8F4"   # these two match --lb-ink in lookbook.css
MIN_CONTRAST = 4.5      # WCAG AA for normal text


def needs_light_text(background):
    """True when the light ink is easier to read on this background than the dark ink."""
    return contrast(background, LIGHT_INK) > contrast(background, DARK_INK)


def best_contrast(background):
    return max(contrast(background, LIGHT_INK), contrast(background, DARK_INK))


def is_readable(background):
    """False for the narrow band of mid-tones where neither ink reaches AA."""
    return best_contrast(background) >= MIN_CONTRAST
