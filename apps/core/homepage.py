"""Homepage content: keys, fallback copy and the context builder.

Everything on the homepage can be changed from the dashboard (Website Content),
stored as SiteContent rows with these keys. When a row (or its image) is missing,
the defaults below are used so the page always renders sensibly.

Hero title: separate lines with a vertical bar, e.g.  Dressed in|quiet confidence
"""
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone

from apps.catalog.models import Category, Product, ProductVariant
from apps.catalog.selectors import storefront_products
from apps.content.models import LOOKBOOK_MAX, LOOKBOOK_MIN, LookbookSlide, SiteContent, SiteSettings
from apps.promotions.models import Promotion

HERO_KEY = "hero"
INTRO_KEY = "intro"
EDITORIAL_KEY = "editorial"
EDITORIAL_DETAIL_KEY = "editorial-detail"

DEFAULTS = {
    HERO_KEY: {
        "eyebrow": "The new season",
        "title": "Dressed in|quiet confidence",
        "body": "Considered pieces for men, women and children, made to be worn, loved and kept.",
    },
    INTRO_KEY: {
        "title": "Clothing with a point of view, and the restraint to let you speak first.",
    },
    EDITORIAL_KEY: {
        "eyebrow": "The AVELLE story",
        "title": "Made slowly. Worn for years.",
        "body": (
            "We believe a wardrobe is built, not bought. Every AVELLE piece is chosen for its cut, "
            "its cloth and the way it settles into a life.\n\n"
            "From a tailored shirt to a christening romper, the idea is the same: fewer, better things."
        ),
    },
}

FEATURED_LIMIT = 8
NEW_LIMIT = 8


def _text(block, field, default_key, default_field):
    value = getattr(block, field, "") if block else ""
    return value or DEFAULTS.get(default_key, {}).get(default_field, "")


def _panel(product):
    """Colours, sizes and stock for the buy panel of a product slide (one query set, prefetched)."""
    variants = [v for v in product.variants.all() if v.is_active]
    rows = []
    for v in variants:
        inventory = getattr(v, "inventory", None)
        rows.append({"id": v.pk, "size": v.size_id, "colour": v.colour_id,
                     "qty": inventory.quantity if inventory else 0, "price": str(v.unit_price)})
    sizes = sorted({v.size for v in variants}, key=lambda s: (s.sort_order, s.name))
    colours = sorted({v.colour for v in variants}, key=lambda c: (c.sort_order, c.name))
    return {"variants": rows, "sizes": sizes, "colours": colours,
            "in_stock": any(r["qty"] > 0 for r in rows), "buyable": bool(rows)}


def build_lookbook():
    """Slides for the carousel hero, or [] when the admin hasn't chosen it or has too few usable slides.

    Each slide gets `.panel` (colours, sizes, stock) when it points at a published product with variants,
    so the hero can offer a real add-to-bag. Anything else gets a plain shop button.
    """
    if SiteSettings.load().hero_style != SiteSettings.HeroStyle.CAROUSEL:
        return []
    queryset = LookbookSlide.objects.filter(is_active=True).select_related("product").prefetch_related(
        "product__variants__size", "product__variants__colour", "product__variants__inventory")
    slides = []
    for slide in queryset[:LOOKBOOK_MAX]:
        if slide.product_id and slide.product.status != Product.Status.PUBLISHED:
            continue  # a draft product would lead to a 404
        slide.panel = _panel(slide.product) if slide.product_id else None
        slides.append(slide)
    return slides if len(slides) >= LOOKBOOK_MIN else []


def lookbook_data(slides):
    """What lookbook.js needs per slide: backdrop colour and the variants for the buy panel."""
    return [{"bg": s.backdrop, "variants": (s.panel or {}).get("variants", [])} for s in slides]


def build_homepage_context():
    blocks = {
        block.key: block
        for block in SiteContent.objects.filter(kind=SiteContent.Kind.HOMEPAGE, is_published=True)
    }

    hero_block = blocks.get(HERO_KEY)
    hero_title = _text(hero_block, "title", HERO_KEY, "title")
    hero = {
        "eyebrow": _text(hero_block, "subtitle", HERO_KEY, "eyebrow"),
        "lines": [line.strip() for line in hero_title.split("|") if line.strip()],
        "body": _text(hero_block, "body", HERO_KEY, "body"),
        "image": hero_block.image if hero_block and hero_block.image else None,
        "is_video": bool(hero_block and hero_block.is_video),
    }

    intro_block = blocks.get(INTRO_KEY)
    intro = _text(intro_block, "title", INTRO_KEY, "title")

    editorial_block = blocks.get(EDITORIAL_KEY)
    detail_block = blocks.get(EDITORIAL_DETAIL_KEY)
    editorial = {
        "eyebrow": _text(editorial_block, "subtitle", EDITORIAL_KEY, "eyebrow"),
        "title": _text(editorial_block, "title", EDITORIAL_KEY, "title"),
        "paragraphs": [p for p in _text(editorial_block, "body", EDITORIAL_KEY, "body").split("\n\n") if p.strip()],
        "image": editorial_block.image if editorial_block and editorial_block.image else None,
        "detail_image": detail_block.image if detail_block and detail_block.image else None,
    }

    # Collections: the top-level categories, each with a live count of published products.
    collections = []
    for category in Category.objects.filter(parent__isnull=True, is_active=True):
        ids = category.get_descendant_ids()
        collections.append(
            {
                "category": category,
                "count": Product.objects.published().filter(category_id__in=ids).count(),
            }
        )

    products = storefront_products()
    now = timezone.now()
    promotions = list(
        Promotion.objects.filter(is_active=True)
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))[:2]
    )

    lookbook = build_lookbook()
    return {
        "hero": hero,
        "lookbook": lookbook,
        "lookbook_data": lookbook_data(lookbook),
        "intro": intro,
        "editorial": editorial,
        "collections": collections,
        "featured_products": list(products.filter(is_featured=True)[:FEATURED_LIMIT]),
        "new_arrivals": list(products.filter(is_new_arrival=True)[:NEW_LIMIT]),
        "promotions": promotions,
    }
