"""Cancel orders that were never paid.

An order sits in ``pending_payment`` while the customer is at Paystack. If they walk away it would sit there
for ever, so this cancels orders older than ``hours``. No stock was taken for an unpaid order, so nothing needs
putting back.

Safety: before cancelling, every unfinished payment attempt is re-checked with Paystack. If the customer actually
paid (callback and webhook both missed), the order is completed instead of cancelled. If Paystack can't be
reached, that order is left alone and tried again on the next run.
"""
import logging
from datetime import timedelta

from django.utils import timezone

from apps.payments.models import Payment
from apps.payments.paystack import PaystackError
from apps.payments.services import verify_reference

from .models import Order
from .services import note_status

log = logging.getLogger(__name__)


def expire_unpaid(hours=48, now=None, dry_run=False):
    """Returns {"cancelled": n, "rescued": n, "skipped": n, "checked": n}."""
    now = now or timezone.now()
    cutoff = now - timedelta(hours=hours)
    result = {"cancelled": 0, "rescued": 0, "skipped": 0, "checked": 0}
    for order in Order.objects.filter(status=Order.Status.PENDING_PAYMENT, created_at__lt=cutoff).order_by("created_at"):
        result["checked"] += 1
        unreachable = False
        for payment in order.payments.filter(status__in=[Payment.Status.INITIATED, Payment.Status.ABANDONED]):
            if dry_run:
                continue
            try:
                verify_reference(payment.reference)
            except PaystackError:
                log.warning("Could not verify %s while expiring %s", payment.reference, order.order_number)
                unreachable = True
        order.refresh_from_db()
        if order.status != Order.Status.PENDING_PAYMENT:
            result["rescued"] += 1  # it was paid after all
            continue
        if unreachable:
            result["skipped"] += 1
            continue
        if not dry_run:
            note_status(order, Order.Status.CANCELLED, f"Expired: not paid within {hours} hours")
            order.status = Order.Status.CANCELLED
            order.cancelled_at = now
            order.save(update_fields=["status", "cancelled_at", "updated_at"])
        result["cancelled"] += 1
    return result
