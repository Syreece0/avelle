"""Cart rules in one place, so views, merge-on-login and (later) checkout agree.

- A line is one product variant. Quantity is limited by stock and MAX_PER_LINE.
- Prices are read live from the variant, never stored in the cart.
- Unavailable lines (unpublished product, inactive variant, no stock) stay visible and
  are excluded from the subtotal, so the customer sees why and can remove them.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum

from apps.catalog.models import Product, ProductVariant

from .models import Cart, CartItem

MAX_PER_LINE = 10
SESSION_KEY = "cart_id"


class CartError(Exception):
    """A problem the customer should be told about, in plain words."""


def get_cart(request, create=False):
    if request.user.is_authenticated:
        if create:
            return Cart.objects.get_or_create(user=request.user)[0]
        return Cart.objects.filter(user=request.user).first()

    cart_id = request.session.get(SESSION_KEY)
    cart = Cart.objects.filter(pk=cart_id, user__isnull=True).first() if cart_id else None
    if cart is None and create:
        if not request.session.session_key:
            request.session.create()
        cart = Cart.objects.get_or_create(session_key=request.session.session_key, user=None)[0]
        request.session[SESSION_KEY] = cart.pk
    return cart


def cart_count(request):
    cart = get_cart(request)
    if cart is None:
        return 0
    return cart.items.aggregate(n=Sum("quantity"))["n"] or 0


def stock_of(variant):
    inventory = getattr(variant, "inventory", None)
    return inventory.quantity if inventory else 0


def is_purchasable(variant):
    return variant.is_active and variant.product.status == Product.Status.PUBLISHED and stock_of(variant) > 0


def _limit(variant):
    return min(stock_of(variant), MAX_PER_LINE)


def resolve_variant(data):
    """Find the variant from a posted variant id, or from product + size + colour."""
    qs = ProductVariant.objects.select_related("product", "size", "colour", "inventory")
    try:
        if data.get("variant"):
            return qs.get(pk=int(data["variant"]))
        return qs.get(product_id=int(data["product"]), size_id=int(data["size"]), colour_id=int(data["colour"]))
    except (KeyError, ValueError, TypeError, ProductVariant.DoesNotExist):
        raise CartError("Please choose a size and colour.")


@transaction.atomic
def add_item(cart, variant, quantity=1):
    """Add to the cart. Returns (item, note) where note explains any adjustment."""
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, quantity)

    if not variant.is_active or variant.product.status != Product.Status.PUBLISHED:
        raise CartError("Sorry, this item is no longer available.")
    limit = _limit(variant)
    if limit <= 0:
        raise CartError("Sorry, that size and colour is sold out.")

    item, created = CartItem.objects.select_for_update().get_or_create(cart=cart, variant=variant, defaults={"quantity": 0})
    wanted = item.quantity + quantity
    note = ""
    if wanted > limit:
        if item.quantity >= limit:
            if created:
                item.delete()
            raise CartError(f"You already have the most we can offer of this item ({limit}).")
        wanted = limit
        note = f"Only {limit} available, so we've set the quantity to {limit}."
    item.quantity = wanted
    item.save(update_fields=["quantity", "updated_at"])
    return item, note


@transaction.atomic
def set_quantity(cart, item_id, quantity):
    item = CartItem.objects.select_related("variant__inventory", "variant__product").filter(cart=cart, pk=item_id).first()
    if item is None:
        raise CartError("That item is no longer in your bag.")
    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        raise CartError("Please enter a quantity.")
    if quantity <= 0:
        item.delete()
        return None, ""
    limit = _limit(item.variant)
    note = ""
    if limit <= 0 or not item.variant.is_active or item.variant.product.status != Product.Status.PUBLISHED:
        raise CartError("This item is no longer available. Please remove it.")
    if quantity > limit:
        quantity, note = limit, f"Only {limit} available."
    item.quantity = quantity
    item.save(update_fields=["quantity", "updated_at"])
    return item, note


def remove_item(cart, item_id):
    CartItem.objects.filter(cart=cart, pk=item_id).delete()


@dataclass
class CartSummary:
    lines: list = field(default_factory=list)
    count: int = 0
    subtotal: Decimal = Decimal("0")
    has_unavailable: bool = False
    notes: list = field(default_factory=list)

    @property
    def is_empty(self):
        return not self.lines


def summarise(cart, reconcile=False):
    """Lines with live prices and availability. With reconcile=True, over-stock quantities are lowered."""
    summary = CartSummary()
    if cart is None:
        return summary
    items = list(
        cart.items.select_related("variant__product__brand", "variant__size", "variant__colour", "variant__inventory")
        .prefetch_related("variant__product__images")
    )
    for item in items:
        variant, product = item.variant, item.variant.product
        stock = stock_of(variant)
        available = is_purchasable(variant)
        quantity = item.quantity
        if reconcile and available and quantity > min(stock, MAX_PER_LINE):
            quantity = min(stock, MAX_PER_LINE)
            item.quantity = quantity
            item.save(update_fields=["quantity", "updated_at"])
            summary.notes.append(f"{product.name}: only {quantity} left, so we've adjusted your quantity.")
        unit = variant.unit_price
        line = {
            "item": item, "product": product, "variant": variant, "image": product.primary_image,
            "quantity": quantity, "unit_price": unit, "line_total": unit * quantity,
            "available": available, "stock": stock, "max": max(1, min(stock, MAX_PER_LINE)),
            "over_stock": available and quantity > min(stock, MAX_PER_LINE),
        }
        summary.lines.append(line)
        summary.count += quantity
        if available:
            summary.subtotal += line["line_total"]
        else:
            summary.has_unavailable = True
            summary.notes.append(f"{product.name} ({variant.size.name}, {variant.colour.name}) is no longer available.")
    return summary


@transaction.atomic
def merge_guest_cart(guest_cart, user):
    """Fold a guest cart into the user's cart on sign-in, respecting stock limits."""
    if guest_cart is None or guest_cart.user_id:
        return
    target, _ = Cart.objects.get_or_create(user=user)
    for item in guest_cart.items.select_related("variant__inventory", "variant__product"):
        try:
            add_item(target, item.variant, item.quantity)
        except CartError:
            continue  # a guest item that can't be added any more is dropped, never an error at sign-in
    guest_cart.delete()
