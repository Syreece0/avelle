import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


def generate_payment_reference():
    return f"AVP-{uuid.uuid4().hex[:20].upper()}"


class Payment(TimeStampedModel):
    """One Paystack transaction attempt for an order.

    The ``reference`` is unique and is what we send to Paystack. An order can
    have several payment rows (failed or abandoned attempts), but at most one
    may ever be successful - enforced below - which prevents double processing.
    """

    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        SUCCESS = "success", "Successful"
        FAILED = "failed", "Failed"
        ABANDONED = "abandoned", "Abandoned"

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    reference = models.CharField(max_length=64, unique=True, default=generate_payment_reference, editable=False)
    provider = models.CharField(max_length=20, default="paystack")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.INITIATED, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.CURRENCY_CODE)
    channel = models.CharField(max_length=30, blank=True)
    gateway_response = models.CharField(max_length=255, blank=True)
    provider_transaction_id = models.CharField(max_length=64, blank=True)
    authorization_url = models.URLField(max_length=500, blank=True)
    raw_response = models.JSONField(default=dict, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["order"],
                condition=Q(status="success"),
                name="payments_one_success_per_order",
            ),
        ]

    def __str__(self):
        return f"{self.reference} ({self.status})"


class Refund(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="refunds")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    provider_reference = models.CharField(max_length=64, blank=True)
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payments_refund_amount_positive"),
        ]

    def __str__(self):
        return f"Refund {self.amount} on {self.payment.reference}"
