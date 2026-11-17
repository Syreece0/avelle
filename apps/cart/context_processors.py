from apps.wishlist.models import WishlistItem

from .services import cart_count


def shopper(request):
    """Bag count for the header badge and the set of wishlisted product ids for the hearts."""
    path = request.path
    if path.startswith(("/dashboard/", "/static/", "/media/", "/django-admin/")):
        return {}
    wishlist_ids = set()
    if request.user.is_authenticated:
        wishlist_ids = set(WishlistItem.objects.filter(wishlist__user=request.user).values_list("product_id", flat=True))
    return {"cart_count": cart_count(request), "wishlist_ids": wishlist_ids}
