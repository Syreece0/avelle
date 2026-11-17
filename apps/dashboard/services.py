"""Dashboard actions that change stock, order state or money.

Each function is atomic, takes row locks where two staff members could collide, and writes the audit
trail (StockAdjustment / OrderStatusHistory). Views call these; they never touch those tables directly.
"""
import logging
from collections import defaultdict
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.catalog.models import Inventory, ProductVariant, StockAdjustment
from apps.orders.models import Order
from apps.orders.services import note_status
from apps.payments.models import Payment, Refund
from apps.payments.paystack import PaystackError
from apps.payments.services import client

from . import rules

log = logging.getLogger(__name__)


class DashboardError(Exception):
    """A rule was broken; the message is written for staff and safe to show."""


# ------------------------------------------------------------------ stock
@transaction.atomic
def adjust_stock(variant_id, *, change=None, set_to=None, reason, note="", user=None, order_number=""):
    """Change one variant's stock by ``change`` (signed) or to ``set_to``. Never goes below zero."""
    if (change is None) == (set_to is None):
        raise ValueError("Give exactly one of change or set_to.")
    inventory, _ = Inventory.objects.select_for_update().get_or_create(variant_id=variant_id)
    new_quantity = set_to if set_to is not None else inventory.quantity + change
    if new_quantity < 0:
        raise DashboardError(f"Only {inventory.quantity} in stock; that would take it below zero.")
    delta = new_quantity - inventory.quantity
    if delta == 0:
        raise DashboardError("That doesn't change the stock level.")
    inventory.quantity = new_quantity
    inventory.save(update_fields=["quantity", "updated_at"])
    StockAdjustment.objects.create(
        variant_id=variant_id, change=delta, quantity_after=new_quantity, reason=reason,
        note=note[:255], order_number=order_number, created_by=user,
    )
    return inventory


@transaction.atomic
def create_variants(product, sizes, colours, *, price_override=None, initial_stock=0, user=None):
    """Create every missing size x colour combination. Returns (created, skipped) counts."""
    existing = set(product.variants.values_list("size_id", "colour_id"))
    created = skipped = 0
    for size in sizes:
        for colour in colours:
            if (size.pk, colour.pk) in existing:
                skipped += 1
                continue
            variant = ProductVariant.objects.create(product=product, size=size, colour=colour, price_override=price_override)
            created += 1
            if initial_stock:
                adjust_stock(variant.pk, change=initial_stock, reason=StockAdjustment.Reason.RESTOCK, note="Opening stock", user=user)
    return created, skipped


def sold_quantities(order):
    """{variant_id: units actually taken from stock for this order and not yet put back}."""
    taken = defaultdict(int)
    rows = StockAdjustment.objects.filter(order_number=order.order_number).values("variant_id", "change", "reason")
    for row in rows:
        if row["reason"] in (StockAdjustment.Reason.SALE, StockAdjustment.Reason.RETURN, StockAdjustment.Reason.CANCELLATION):
            taken[row["variant_id"]] -= row["change"]  # sale is negative, so this adds; returns subtract
    return {k: v for k, v in taken.items() if v > 0}


def restock_order(order, user, reason=StockAdjustment.Reason.RETURN, note="Order refunded"):
    """Put back exactly what this order took (never more). Returns units restocked."""
    restocked = 0
    for variant_id, qty in sold_quantities(order).items():
        adjust_stock(variant_id, change=qty, reason=reason, note=note, user=user, order_number=order.order_number)
        restocked += qty
    return restocked


# ------------------------------------------------------------------ customer messages
def _notify_status(order_id):
    """Emails must never undo a status change, so failures are logged and swallowed."""
    try:
        from apps.notifications.services import notify_order_status

        notify_order_status(Order.objects.get(pk=order_id))
    except Exception:  # noqa: BLE001
        log.exception("Status notification failed for order id %s", order_id)


def _notify_refund(order_id, refund_id):
    try:
        from apps.notifications.services import notify_refund

        notify_refund(Order.objects.get(pk=order_id), Refund.objects.get(pk=refund_id))
    except Exception:  # noqa: BLE001
        log.exception("Refund notification failed for refund id %s", refund_id)


# ------------------------------------------------------------------ orders
@transaction.atomic
def change_order_status(order_id, target, *, user, note="", courier="", tracking_number=""):
    order = Order.objects.select_for_update().get(pk=order_id)
    if not rules.can_transition(order.status, target):
        label = dict(Order.Status.choices).get(target, target)
        raise DashboardError(f"An order that is {order.get_status_display().lower()} can't be moved to {label.lower()}.")
    now = timezone.now()
    update = ["status", "updated_at"]
    if target == Order.Status.SHIPPED:
        order.shipped_at = now
        order.courier = courier.strip()
        order.tracking_number = tracking_number.strip()
        update += ["shipped_at", "courier", "tracking_number"]
        detail = " ".join(p for p in (courier.strip(), tracking_number.strip()) if p)
        note = note or (f"Shipped: {detail}" if detail else "Shipped")
    elif target == Order.Status.DELIVERED:
        order.delivered_at = now
        update.append("delivered_at")
    elif target == Order.Status.CANCELLED:
        order.cancelled_at = now
        update.append("cancelled_at")
    note_status(order, target, note, user=user)  # records from_status before we overwrite it
    order.status = target
    order.save(update_fields=update)
    transaction.on_commit(lambda: _notify_status(order.pk))
    return order


@transaction.atomic
def update_tracking(order_id, *, user, courier, tracking_number):
    order = Order.objects.select_for_update().get(pk=order_id)
    if order.status not in (Order.Status.SHIPPED, Order.Status.DELIVERED):
        raise DashboardError("Tracking can be edited once the order has shipped.")
    order.courier, order.tracking_number = courier.strip(), tracking_number.strip()
    order.save(update_fields=["courier", "tracking_number", "updated_at"])
    note_status(order, order.status, f"Tracking updated: {order.courier} {order.tracking_number}".strip(), user=user)
    return order


# ------------------------------------------------------------------ refunds
def _mark_refund(refund, provider_status, provider_id=""):
    """Map a Paystack refund status onto ours."""
    if provider_id:
        refund.provider_reference = str(provider_id)[:64]
    if provider_status == "processed":
        refund.status = Refund.Status.COMPLETED
    elif provider_status == "failed":
        refund.status = Refund.Status.FAILED
    else:
        refund.status = Refund.Status.PENDING  # pending / processing / needs-attention


def refunded_so_far(payment):
    return list(payment.refunds.exclude(status=Refund.Status.FAILED).values_list("amount", flat=True))


def refund_order(order_id, *, amount, reason, user, restock=False):
    """Refund (part of) an order's successful payment through Paystack.

    The refund row is saved *before* calling Paystack so a crash mid-request can't lose track of it,
    and the Paystack call itself is outside the DB transaction so a slow gateway holds no locks.
    """
    amount = Decimal(amount)
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        if order.status not in rules.REFUNDABLE_ORDER_STATUSES:
            raise DashboardError("Only paid orders can be refunded.")
        payment = order.payments.select_for_update().filter(status=Payment.Status.SUCCESS).first()
        if payment is None:
            raise DashboardError("This order has no successful payment to refund.")
        left = rules.refundable_amount(payment.amount, refunded_so_far(payment))
        if amount <= 0:
            raise DashboardError("Enter an amount greater than zero.")
        if amount > left:
            raise DashboardError(f"Only {settings.CURRENCY_SYMBOL}{left:,.2f} is still refundable on this payment.")
        refund = Refund.objects.create(payment=payment, amount=amount, reason=reason[:255], processed_by=user)
        payment_ref = payment.reference

    try:
        data = client().refund(transaction=payment_ref, amount=amount, note=reason)
    except PaystackError as error:
        log.error("Paystack refund failed for %s: %s", payment_ref, error)
        Refund.objects.filter(pk=refund.pk).update(status=Refund.Status.FAILED)
        raise DashboardError("Paystack didn't accept the refund. Nothing was refunded; you can try again.") from error

    with transaction.atomic():
        refund = Refund.objects.select_for_update().get(pk=refund.pk)
        _mark_refund(refund, data.get("status", ""), data.get("id", ""))
        refund.save()
        order = Order.objects.select_for_update().get(pk=order_id)
        payment = Payment.objects.get(pk=payment.pk)
        full = rules.refund_is_full(payment.amount, refunded_so_far(payment))
        note = f"Refund of {settings.CURRENCY_SYMBOL}{amount:,.2f} started" + (f": {reason}" if reason else "")
        if full:
            note_status(order, Order.Status.REFUNDED, note, user=user)
            order.status = Order.Status.REFUNDED
            order.save(update_fields=["status", "updated_at"])
            if restock:
                restock_order(order, user)
        else:
            note_status(order, order.status, note + " (partial)", user=user)
    _notify_refund(order_id, refund.pk)
    return refund


def apply_refund_event(event_name, data):
    """Webhook: Paystack tells us a refund finished or failed. Unknown refunds are ignored."""
    ref = str(data.get("id") or data.get("refund_reference") or "")
    txn = data.get("transaction_reference") or (data.get("transaction") or {}).get("reference", "")
    refund = None
    if ref:
        refund = Refund.objects.filter(provider_reference=ref).first()
    if refund is None and txn:
        refund = Refund.objects.filter(payment__reference=txn, status=Refund.Status.PENDING).order_by("-created_at").first()
    if refund is None:
        return None
    _mark_refund(refund, "processed" if event_name == "refund.processed" else "failed" if event_name == "refund.failed" else "pending", ref)
    refund.save()
    return refund


# ------------------------------------------------------------------ customers / team
def admin_count():
    from django.contrib.auth import get_user_model

    User = get_user_model()
    return User.objects.filter(is_active=True, role=User.Role.ADMIN).count()


def total_stock(product):
    return product.variants.aggregate(n=Sum("inventory__quantity"))["n"] or 0
