"""Generate tasteful tonal placeholder images for demo data (Pillow only).

These are stand-ins for real photography so the storefront can be reviewed before
the business uploads its own images. Every image carries a small "DEMO IMAGE" label.
"""
import io

from PIL import Image, ImageDraw, ImageFilter, ImageFont

# Garment silhouettes as polygons in a 100 x 100 box.
SHAPES = {
    "shirt": [(38, 8), (50, 14), (62, 8), (86, 24), (78, 40), (68, 34), (68, 92), (32, 92), (32, 34), (22, 40), (14, 24)],
    "jacket": [(38, 8), (50, 16), (62, 8), (88, 30), (82, 86), (70, 84), (68, 94), (32, 94), (30, 84), (18, 86), (12, 30)],
    "dress": [(40, 6), (46, 6), (50, 12), (54, 6), (60, 6), (62, 30), (58, 40), (76, 94), (24, 94), (42, 40), (38, 30)],
    "trouser": [(32, 6), (68, 6), (72, 94), (54, 94), (50, 38), (46, 94), (28, 94)],
    "skirt": [(34, 10), (66, 10), (80, 92), (20, 92)],
    "shoe": [(8, 66), (30, 46), (46, 48), (60, 62), (90, 68), (92, 82), (8, 82)],
    "romper": [(36, 10), (44, 14), (50, 10), (56, 14), (64, 10), (74, 26), (66, 32), (64, 50), (70, 86), (54, 86), (50, 64), (46, 86), (30, 86), (36, 50), (34, 32), (26, 26)],
    "set": [(36, 6), (64, 6), (70, 30), (62, 36), (62, 48), (78, 94), (22, 94), (38, 48), (38, 36), (30, 30)],
    "cap": [(14, 62), (22, 40), (40, 28), (60, 28), (78, 40), (86, 62), (96, 66), (96, 72), (14, 72)],
}


def _hex(value):
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _font(size):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow
        return ImageFont.load_default()


def _scaled(points, box):
    x0, y0, x1, y1 = box
    return [(x0 + px / 100 * (x1 - x0), y0 + py / 100 * (y1 - y0)) for px, py in points]


def _label(draw, w, h, colour):
    size = max(11, w // 70)
    draw.text((w * 0.05, h - size * 2.4), "DEMO IMAGE", fill=colour, font=_font(size))


def _jpeg(img):
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, "JPEG", quality=86, optimize=True)
    return buffer.getvalue()


def _shadow(img, box, strength=60):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    x0, y0, x1, y1 = box
    ImageDraw.Draw(layer).ellipse((x0 + (x1 - x0) * 0.12, y1 - 24, x1 - (x1 - x0) * 0.12, y1 + 24), fill=(23, 23, 23, strength))
    layer = layer.filter(ImageFilter.GaussianBlur(20))
    img.alpha_composite(layer)


def product_image(kind, bg, fg, size=(960, 1200), pose=0):
    """A single garment silhouette on a flat tonal background."""
    w, h = size
    img = Image.new("RGBA", size, _hex(bg) + (255,))
    draw = ImageDraw.Draw(img)
    pad_x, pad_y = w * 0.2, h * 0.17
    box = (pad_x, pad_y, w - pad_x, h - pad_y * 1.15)
    if pose == 1:  # alternate view: slightly smaller, shifted
        box = (pad_x * 1.3, pad_y * 1.2, w - pad_x * 1.3, h - pad_y * 1.4)
    _shadow(img, box)
    draw = ImageDraw.Draw(img)
    if kind == "bag":
        x0, y0, x1, y1 = box
        bw = (x1 - x0)
        draw.arc((x0 + bw * 0.28, y0 + (y1 - y0) * 0.16, x1 - bw * 0.28, y0 + (y1 - y0) * 0.62), 180, 360, fill=_hex(fg), width=max(8, w // 70))
        draw.rounded_rectangle((x0 + bw * 0.08, y0 + (y1 - y0) * 0.38, x1 - bw * 0.08, y1), radius=18, fill=_hex(fg))
    else:
        draw.polygon(_scaled(SHAPES[kind], box), fill=_hex(fg))
    _label(draw, w, h, _hex(fg))
    return _jpeg(img)


def scene_image(size, bg, shapes, label_colour):
    """A wide or tall tonal composition: list of (type, color, params) layers."""
    w, h = size
    img = Image.new("RGBA", size, _hex(bg) + (255,))
    draw = ImageDraw.Draw(img)
    for layer in shapes:
        kind, colour = layer[0], _hex(layer[1])
        if kind == "arch":  # rounded-top rectangle: x0,y0,x1,y1 as fractions
            x0, y0, x1, y1 = [v * (w if i % 2 == 0 else h) for i, v in enumerate(layer[2])]
            radius = (x1 - x0) / 2
            draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=colour)
            draw.rectangle((x0, y0 + radius, x1, y1), fill=colour)
        elif kind == "rect":
            x0, y0, x1, y1 = [v * (w if i % 2 == 0 else h) for i, v in enumerate(layer[2])]
            draw.rectangle((x0, y0, x1, y1), fill=colour)
        elif kind == "circle":
            cx, cy, r = layer[2][0] * w, layer[2][1] * h, layer[2][2] * min(w, h)
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=colour)
        elif kind in SHAPES:
            x0, y0, x1, y1 = [v * (w if i % 2 == 0 else h) for i, v in enumerate(layer[2])]
            draw.polygon(_scaled(SHAPES[kind], (x0, y0, x1, y1)), fill=colour)
    _label(draw, w, h, _hex(label_colour))
    return _jpeg(img)


def hero_image():
    return scene_image(
        (1920, 1080),
        "#2A2622",
        [
            ("arch", "#37322C", (0.52, 0.10, 0.90, 1.2)),
            ("circle", "#312C26", (0.30, 0.55, 0.30)),
            ("dress", "#4B443B", (0.55, 0.12, 0.88, 0.98)),
        ],
        "#5C554A",
    )


def collection_image(kind, bg, fg):
    return scene_image(
        (900, 1200),
        bg,
        [("arch", fg, (0.16, 0.10, 0.84, 1.2)), (kind, "#171717", (0.26, 0.22, 0.74, 0.86))],
        "#8A8072",
    )


def editorial_image():
    return scene_image(
        (1000, 1300),
        "#D8CDBB",
        [("arch", "#E9E1D5", (0.14, 0.08, 0.86, 1.2)), ("jacket", "#2B2723", (0.24, 0.20, 0.76, 0.86))],
        "#8A8072",
    )


def editorial_detail_image():
    return scene_image(
        (700, 900),
        "#BFB19B",
        [("circle", "#CDBFA8", (0.5, 0.45, 0.34)), ("shoe", "#2B2723", (0.14, 0.38, 0.86, 0.72))],
        "#6E6454",
    )


def promo_image(bg, fg, kind):
    return scene_image(
        (1600, 700),
        bg,
        [("arch", fg, (0.60, 0.08, 0.86, 1.3)), (kind, "#171717", (0.64, 0.14, 0.82, 0.92))],
        "#8A8072",
    )
