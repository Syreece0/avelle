"""Payment processing. Everything that changes money or stock goes through apply_gateway_result().

Safety properties:
- Idempotent: the browser callback and the webhook can both arrive, in any order, any number of
  times; the order is marked paid, stock is taken and the code redeemed exactly once.
- Never trusts the browser or the webhook body: the result is always re-fetched from Paystack
  (verify), and the amount and currency must match the order exactly.
- At most one successful payment per order (database constraint); a second successful charge
  for an already-paid order is recorded as a duplicate needing a refund, never as a second sale.
"""
import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.catalog.models import Inventory, StockAdjustment
from apps.orders.models import Order
from apps.orders.services import note_status
from apps.promotions.models import DiscountCode, DiscountRedemption

from .models import Payment
from .paystack import PaystackClient, PaystackError, to_kobo

log = logging.getLogger(__name__)


class PaymentError(Exception):
    """Safe to show to the customer."""


def client():
    return PaystackClient(settings.PAYSTACK_SECRET_KEY, settings.PAYSTACK_BASE_URL)


def start_payment(order):
    """Create a Payment attempt and return the Paystack checkout URL."""
    if order.status != Order.Status.PENDING_PAYMENT:
        raise PaymentError("This order doesn't need payment.")
    payment = Payment.objects.create(order=order, amount=order.total, currency=order.currency)
    try:
        data = client().initialize(
            email=order.email, amount=order.total, reference=payment.reference, currency=order.currency,
            callback_url=settings.SITE_URL.rstrip("/") + "/payments/callback/",
            metadata={"order_number": order.order_number},
        )
    except PaystackError as error:
        log.error("Paystack initialize failed for %s: %s", order.order_number, error)
        payment.status = Payment.Status.FAILED
        payment.gateway_response = str(error)[:255]
        payment.save(update_fields=["status", "gateway_response", "updated_at"])
        raise PaymentError("We couldn't start the payment just now. Please try again in a moment.") from error
    payment.authorization_url = data["authorization_url"]
    payment.save(update_fields=["authorization_url", "updated_at"])
    return payment.authorization_url


def reconcile_order(order, *, max_attempts=4, timeout=8):
    """Ask Paystack about every unsettled payment of an order and apply what it says.

    This is the safety net for when the browser callback or the webhook never arrived (a bank transfer
    paid in the banking app, a closed tab, a webhook URL that isn't set up). Returns True if the order is paid.
    Never raises: a Paystack outage must not break the page that called it.
    """
    order.refresh_from_db()
    if order.is_paid:
        return True
    cutoff = timezone.now() - timedelta(days=7)
    attempts = (Payment.objects.filter(order=order, created_at__gte=cutoff).exclude(status=Payment.Status.SUCCESS)
                .order_by("-created_at")[:max_attempts])
    for payment in attempts:
        try:
            data = PaystackClient(settings.PAYSTACK_SECRET_KEY, settings.PAYSTACK_BASE_URL, timeout=timeout).verify(payment.reference)
            apply_gateway_result(payment.pk, data)
        except PaystackError as error:
            log.warning("Could not reconcile %s: %s", payment.reference, error)
        except Exception:  # noqa: BLE001
            log.exception("Reconcile failed for %s", payment.reference)
        order.refresh_from_db()
        if order.is_paid:
            return True
    return False


def verify_reference(reference):
    """Fetch the truth from Paystack and apply it. Returns the Payment (or None if unknown)."""
    payment = Payment.objects.filter(reference=reference).select_related("order").first()
    if payment is None:
        return None
    data = client().verify(reference)  # PaystackError propagates so the caller can retry later
    apply_gateway_result(payment.pk, data)
    return Payment.objects.select_related("order").get(pk=payment.pk)


@transaction.atomic
def apply_gateway_result(payment_id, data):
    payment = Payment.objects.select_for_update().select_related("order").get(pk=payment_id)
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    if payment.status == Payment.Status.SUCCESS:
        return payment  # already processed

    gateway_status = data.get("status", "")
    payment.verified_at = timezone.now()
    payment.channel = data.get("channel", "") or ""
    payment.gateway_response = (data.get("gateway_response") or gateway_status)[:255]
    payment.provider_transaction_id = str(data.get("id", ""))[:64]
    payment.raw_response = data

    if gateway_status != "success":
        payment.status = Payment.Status.ABANDONED if gateway_status in ("abandoned", "pending", "ongoing", "") else Payment.Status.FAILED
        payment.save()
        return payment

    # Money was taken: make sure it is the right money.
    if data.get("amount") != to_kobo(payment.amount) or (data.get("currency") or payment.currency) != payment.currency:
        log.error("Amount mismatch for %s: gateway %s vs expected %s", payment.reference, data.get("amount"), to_kobo(payment.amount))
        payment.status = Payment.Status.FAILED
        payment.gateway_response = "Amount mismatch: needs manual review"
        payment.save()
        note_status(order, order.status, f"Payment {payment.reference} amount mismatch; review in Paystack.")
        return payment

    if order.is_paid or order.status in (Order.Status.CANCELLED, Order.Status.REFUNDED):
        payment.status = Payment.Status.FAILED
        payment.gateway_response = "Duplicate or late payment: refund required"
        payment.save()
        note_status(order, order.status, f"Extra successful payment {payment.reference}: refund required.")
        return payment

    now = timezone.now()
    payment.status = Payment.Status.SUCCESS
    payment.paid_at = now
    payment.save()

    shortages = consume_stock(order)
    note_status(order, Order.Status.PAID, f"Payment received ({payment.channel or 'online'}), ref {payment.reference}")
    order.status = Order.Status.PAID
    order.paid_at = now
    order.save(update_fields=["status", "paid_at", "updated_at"])
    if shortages:
        note_status(order, Order.Status.PAID, "STOCK SHORTFALL, review before fulfilling: " + "; ".join(shortages))
    redeem_code(order)
    transaction.on_commit(lambda: _after_paid(order.pk))
    return payment


def consume_stock(order):
    """Take stock for each line (sale rows in the stock history). Returns human-readable shortfalls."""
    shortages = []
    items = sorted((i for i in order.items.all() if i.variant_id), key=lambda i: i.variant_id)  # stable lock order
    for item in items:
        inv = Inventory.objects.select_for_update().filter(variant_id=item.variant_id).first()
        if inv is None:
            shortages.append(f"{item.product_name} ({item.size_name}, {item.colour_name}): no stock record")
            continue
        take = min(inv.quantity, item.quantity)
        if take < item.quantity:
            shortages.append(f"{item.product_name} ({item.size_name}, {item.colour_name}): ordered {item.quantity}, had {inv.quantity}")
        if take:
            inv.quantity -= take
            inv.save(update_fields=["quantity", "updated_at"])
            StockAdjustment.objects.create(
                variant_id=item.variant_id, change=-take, quantity_after=inv.quantity,
                reason=StockAdjustment.Reason.SALE, order_number=order.order_number, note="Order paid",
            )
    return shortages


def redeem_code(order):
    if not order.discount_code_text:
        return
    code = DiscountCode.objects.select_for_update().filter(code=order.discount_code_text).first()
    if code is None:
        return
    _, created = DiscountRedemption.objects.get_or_create(
        order=order, defaults={"code": code, "user": order.user, "email": order.email, "amount": order.discount_amount},
    )
    if created:
        DiscountCode.objects.filter(pk=code.pk).update(times_used=F("times_used") + 1)


def _after_paid(order_id):
    """Emails and notifications must never undo a payment, so failures are logged and swallowed."""
    try:
        from apps.notifications.services import notify_order_paid

        notify_order_paid(Order.objects.prefetch_related("items").get(pk=order_id))
    except Exception:  # noqa: BLE001
        log.exception("Order paid notification failed for order id %s", order_id)
