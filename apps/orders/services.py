"""Checkout rules: delivery quote, discount codes and order creation."""
from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.promotions.models import DiscountCode, DiscountRedemption

from .models import DeliveryZone, Order, OrderItem, OrderStatusHistory

ZERO = Decimal("0.00")


class CheckoutError(Exception):
    """A problem the customer should be told about."""


@dataclass
class Quote:
    subtotal: Decimal
    discount: Decimal
    delivery: Decimal | None   # None until a state is chosen
    total: Decimal | None
    zone: object = None
    code: object = None
    code_message: str = ""
    eta: str = ""
    free_delivery: bool = False


def zone_for(state):
    return DeliveryZone.objects.filter(state=state, is_active=True).first() if state else None


def validate_code(text, subtotal, user=None, email=""):
    """Return (DiscountCode or None, message). The message is shown to the customer either way."""
    text = (text or "").strip().upper()
    if not text:
        return None, ""
    code = DiscountCode.objects.filter(code=text, is_active=True).first()
    now = timezone.now()
    if code is None:
        return None, "That code isn't valid."
    if code.starts_at and code.starts_at > now:
        return None, "That code isn't active yet."
    if code.expires_at and code.expires_at <= now:
        return None, "That code has expired."
    if subtotal < code.minimum_subtotal:
        return None, f"This code needs a minimum order of ₦{code.minimum_subtotal:,.0f}."
    if code.usage_limit is not None and code.times_used >= code.usage_limit:
        return None, "That code has been fully redeemed."
    who = Q(user=user) if user is not None and user.is_authenticated else Q(email__iexact=email) if email else None
    if who is not None and DiscountRedemption.objects.filter(code=code).filter(who).count() >= code.per_user_limit:
        return None, "You've already used that code."
    return code, f"Code {code.code} applied."


def build_quote(subtotal, state="", code_text="", user=None, email=""):
    code, message = validate_code(code_text, subtotal, user, email)
    discount = code.discount_for(subtotal) if code else ZERO
    zone = zone_for(state)
    delivery = zone.charge_for(subtotal - discount) if zone else None
    total = (subtotal - discount + delivery) if delivery is not None else None
    eta = ""
    if zone:
        lo, hi = zone.estimated_days_min, zone.estimated_days_max
        eta = f"{lo} to {hi} working days" if lo != hi else f"{lo} working days"
    return Quote(subtotal, discount, delivery, total, zone, code, message if code_text.strip() else "", eta,
                 free_delivery=bool(zone and delivery == ZERO))


def note_status(order, to_status, note="", user=None):
    OrderStatusHistory.objects.create(order=order, from_status=order.status if order.pk and order.status != to_status else "",
                                      to_status=to_status, note=note, changed_by=user)


@transaction.atomic
def create_order(*, user, summary, details, quote):
    """Create a pending-payment order from the current bag. Stock is NOT taken yet (see payments)."""
    if summary.is_empty:
        raise CheckoutError("Your bag is empty.")
    if summary.has_unavailable or any(line["over_stock"] for line in summary.lines):
        raise CheckoutError("Some items in your bag are no longer available in that quantity. Please review your bag.")
    if quote.zone is None or quote.total is None:
        raise CheckoutError("We don't deliver to that state yet.")

    order = Order.objects.create(
        user=user if user is not None and user.is_authenticated else None,
        email=details["email"], customer_name=details["customer_name"], phone=details["phone"],
        address_line1=details["address_line1"], address_line2=details.get("address_line2", ""),
        city=details["city"], state=details["state"], landmark=details.get("landmark", ""),
        delivery_note=details.get("delivery_note", ""),
        delivery_zone=quote.zone, delivery_zone_name=quote.zone.state,
        subtotal=summary.subtotal, discount_amount=quote.discount, delivery_charge=quote.delivery, total=quote.total,
        discount_code_text=quote.code.code if quote.code else "",
    )
    OrderItem.objects.bulk_create([
        OrderItem(
            order=order, variant=line["variant"], product=line["product"], product_name=line["product"].name,
            sku=line["variant"].sku, size_name=line["variant"].size.name, colour_name="" if line["variant"].colour.is_standard else line["variant"].colour.name,
            image_url=line["image"].image.url if line["image"] else "",
            unit_price=line["unit_price"], quantity=line["quantity"], line_total=line["line_total"],
        )
        for line in summary.lines
    ])
    OrderStatusHistory.objects.create(order=order, from_status="", to_status=Order.Status.PENDING_PAYMENT, note="Order placed", changed_by=None)
    return order


def user_can_view(request, order):
    """Owners see their orders; guests see only orders placed in their own session."""
    if request.user.is_authenticated and order.user_id == request.user.pk:
        return True
    return order.order_number in request.session.get("order_numbers", [])


def remember_order(request, order):
    numbers = request.session.get("order_numbers", [])
    if order.order_number not in numbers:
        numbers.append(order.order_number)
    request.session["order_numbers"] = numbers[-20:]
