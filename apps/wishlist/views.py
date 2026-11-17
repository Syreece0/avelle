from django.db import IntegrityError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.http import urlencode
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from apps.catalog.models import Product
from apps.catalog.selectors import storefront_products

from .models import Wishlist, WishlistItem


@login_required
def wishlist_page(request):
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
    ids = list(wishlist.items.values_list("product_id", flat=True))
    by_id = {p.pk: p for p in storefront_products().filter(pk__in=ids)}
    products = [by_id[i] for i in ids if i in by_id]  # newest saved first; unpublished products are hidden
    return render(request, "wishlist/wishlist.html", {"products": products})


@require_POST
def toggle(request):
    if not request.user.is_authenticated:
        login_url = f"{reverse('accounts:login')}?{urlencode({'next': request.POST.get('next') or '/wishlist/'})}"
        return JsonResponse({"ok": False, "login_required": True, "login_url": login_url}, status=401)
    try:
        product = get_object_or_404(Product.objects.published(), pk=int(request.POST.get("product", "0")))
    except ValueError:
        return JsonResponse({"ok": False}, status=400)
    wishlist, _ = Wishlist.objects.get_or_create(user=request.user)
    existing = WishlistItem.objects.filter(wishlist=wishlist, product=product)
    if existing.exists():
        existing.delete()
        active = False
    else:
        try:
            WishlistItem.objects.create(wishlist=wishlist, product=product)
        except IntegrityError:  # double-click race: it is saved either way
            pass
        active = True
    return JsonResponse({"ok": True, "active": active, "count": wishlist.items.count()})
