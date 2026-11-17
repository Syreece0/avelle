import json

from django.conf import settings
from django.db.models import Avg, Count
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET

from .models import Product, ProductVariant, Review
from .selectors import related_products, search_products, storefront_products, suggest


def _wants_json(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest" or request.GET.get("format") == "json"


@require_GET
def shop(request):
    result = search_products(request.GET)
    context = {"result": result, "f": result.filters, "products": result.page.object_list,
               "currency_symbol": settings.CURRENCY_SYMBOL}

    if _wants_json(request):
        render_part = lambda name: render_to_string(name, context, request=request)
        return JsonResponse({
            "results_html": render_part("shop/_results.html"),
            "chips_html": render_part("shop/_chips.html"),
            "types_html": render_part("shop/_types.html"),
            "pagination_html": render_part("shop/_pagination.html"),
            "total": result.total,
            "heading": result.heading,
            "page": result.page.number,
            "next_url": result.next_query,
            "active_count": result.filters.active_count,
            "tabs": result.tabs,
            "all_count": result.all_count,
            "all_href": result.all_href,
            "facets": {
                "sizes": {o["value"]: o["count"] for g in result.facets["sizes"] for o in g["options"]},
                "colours": {o["value"]: o["count"] for o in result.facets["colours"]},
                "brands": {o["value"]: o["count"] for o in result.facets["brands"]},
            },
            "query": result.filters.query_string(),
            "scope": f"{result.filters.category}/{result.filters.type}",
            "filters_html": render_part("shop/_filters_fields.html"),
            "sorts": result.sorts,
        })

    return render(request, "shop/shop.html", context)


@require_GET
def suggest_view(request):
    data = suggest(request.GET.get("q", ""))
    return JsonResponse({
        "products": [
            {
                "name": p.name,
                "url": p.get_absolute_url(),
                "price": f"{settings.CURRENCY_SYMBOL}{p.effective_price:,.0f}",
                "image": p.primary_image.image.url if p.primary_image else "",
            }
            for p in data["products"]
        ],
        "categories": data["categories"],
    })


def product_detail(request, slug):
    product = get_object_or_404(
        storefront_products().prefetch_related("variants__size", "variants__colour", "variants__inventory"),
        slug=slug,
    )

    variants = [v for v in product.variants.all() if v.is_active]
    matrix = []
    for v in variants:
        inventory = getattr(v, "inventory", None)
        matrix.append({
            "id": v.pk, "size": v.size_id, "colour": v.colour_id,
            "qty": inventory.quantity if inventory else 0,
            "price": str(v.unit_price),
            "low": bool(inventory and inventory.is_low_stock),
        })

    sizes = sorted({v.size for v in variants}, key=lambda s: (s.sort_order, s.name))
    colours = sorted({v.colour for v in variants}, key=lambda c: (c.sort_order, c.name))
    images = list(product.images.all())

    reviews_qs = Review.objects.filter(product=product, is_approved=True).select_related("user")
    summary = reviews_qs.aggregate(avg=Avg("rating"), n=Count("pk"))
    reviews = []
    for r in reviews_qs[:10]:
        first = (r.user.first_name or "").strip()
        last = (r.user.last_name or "").strip()
        name = f"{first} {last[:1]}." if first and last else (first or "Verified customer")
        reviews.append({"name": name, "rating": r.rating, "title": r.title, "body": r.body,
                        "date": r.created_at, "verified": r.is_verified_purchase})

    category = product.category
    crumbs = []
    node = category
    while node is not None:
        crumbs.insert(0, node)
        node = node.parent
    root = crumbs[0] if crumbs else None

    first_image = images[0] if images else None
    in_stock = bool(product.in_stock)
    ld = {
        "@context": "https://schema.org", "@type": "Product", "name": product.name,
        "description": (product.short_description or product.description or product.name)[:300],
        "image": [request.build_absolute_uri(i.image.url) for i in images[:4]],
        "brand": {"@type": "Brand", "name": product.brand.name} if product.brand else None,
        "offers": {
            "@type": "Offer", "priceCurrency": settings.CURRENCY_CODE, "price": str(product.current_price),
            "availability": "https://schema.org/InStock" if in_stock else "https://schema.org/OutOfStock",
            "url": request.build_absolute_uri(product.get_absolute_url()),
        },
    }
    if summary["n"]:
        ld["aggregateRating"] = {"@type": "AggregateRating", "ratingValue": round(summary["avg"], 1), "reviewCount": summary["n"]}
    ld = {k: v for k, v in ld.items() if v}
    # "<" escaped so a product name can never close the script element
    json_ld = json.dumps(ld).replace("<", "\\u003c")

    context = {
        "json_ld": json_ld,
        "currency_symbol": settings.CURRENCY_SYMBOL,
        "og_image": request.build_absolute_uri(first_image.image.url) if first_image else "",
        "product": product,
        "matrix_json": matrix,
        "images": images,
        "images_json": [{"id": i.pk, "colour": i.colour_id, "alt": i.alt_text or product.name} for i in images],
        "sizes": sizes,
        "colours": colours,
        "single_size": len(sizes) == 1,
        "single_colour": len(colours) == 1,
        "crumbs": crumbs,
        "root": root,
        "size_guide": category.get_size_guide() if category else "",
        "reviews": reviews,
        "rating_avg": round(summary["avg"], 1) if summary["avg"] else None,
        "rating_count": summary["n"],
        "related": related_products(product),
        "any_stock": product.in_stock,
    }
    return render(request, "shop/product_detail.html", context)
