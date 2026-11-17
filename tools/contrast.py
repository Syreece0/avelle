#!/usr/bin/env python3
"""WCAG contrast check for the colour pairs the design uses (AA: 4.5 for body text, 3.0 for large text and UI parts)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
css = (ROOT / "static/css/tokens.css").read_text() + (ROOT / "static/css/dashboard.css").read_text()
VARS = dict(re.findall(r"--([\w-]+)\s*:\s*(#[0-9A-Fa-f]{6})\b", css))


def lum(hex_):
    r, g, b = (int(hex_[i:i + 2], 16) / 255 for i in (1, 3, 5))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def ratio(a, b):
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def v(name):
    return VARS[name] if name in VARS else name


PAIRS = [  # (text, background, minimum, label)
    ("ink", "ivory", 4.5, "body text on page"), ("ink", "white", 4.5, "body text on cards"), ("ink", "champagne", 4.5, "text on champagne"),
    ("grey-text", "ivory", 4.5, "secondary text on page"), ("grey-text", "white", 4.5, "secondary text on cards"),
    ("ivory", "ink", 4.5, "text on near-black"), ("gold", "ink", 4.5, "gold text on near-black (sidebar tag)"),
    ("gold-text", "ivory", 4.5, "gold text on page (the darkened token)"), ("gold-text", "white", 4.5, "gold text on cards"), ("gold-text", "gold-soft", 4.5, "gold text on soft gold"), ("ink", "gold", 4.5, "ink on gold (badges, bell count)"),
    ("danger", "white", 4.5, "error text"), ("success", "white", 4.5, "success text"),
    ("st-pending-fg", "st-pending-bg", 4.5, "badge pending"), ("st-paid-fg", "st-paid-bg", 4.5, "badge paid"),
    ("st-processing-fg", "st-processing-bg", 4.5, "badge processing"), ("st-shipped-fg", "st-shipped-bg", 4.5, "badge shipped"),
    ("st-delivered-fg", "st-delivered-bg", 4.5, "badge delivered"), ("st-cancelled-fg", "st-cancelled-bg", 4.5, "badge cancelled"),
    ("st-refunded-fg", "st-refunded-bg", 4.5, "badge refunded"), ("warning", "warning-soft", 4.5, "low-stock badge"),
    ("danger", "danger-soft", 4.5, "danger alert"),
    # Glass theme: darkest the page glow gets behind translucent panels (the champagne wash at the page bottom)
    ("ink", "#E9E1D5", 4.5, "glass: text on darkest backdrop"), ("grey-text", "#E9E1D5", 4.5, "glass: secondary text on darkest backdrop"),
    ("gold-text", "#E9E1D5", 4.5, "glass: gold text on darkest backdrop"), ("grey-text", "#F1ECE2", 4.5, "glass: secondary text on lower backdrop"),
]
bad = 0
for fg, bg, minimum, label in PAIRS:
    try:
        r = ratio(v(fg), v(bg))
    except KeyError as e:
        print(f"skip   {label}: unknown colour {e}")
        continue
    ok = r >= minimum
    bad += not ok
    print(f"{'ok  ' if ok else 'FAIL'}  {r:5.2f}  (needs {minimum})  {label}: {v(fg)} on {v(bg)}")
sys.exit(1 if bad else 0)
