from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import TimeStampedModel


class Notification(TimeStampedModel):
    """In-app notification plus a record of whether the matching email went out.

    ``dedupe_key`` identifies an event (e.g. ``order-paid:AV-7K3Q9XD2``). It is
    unique per recipient, so retrying a webhook or re-saving an order can never
    create or email the same notification twice.
    """

    class Audience(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        ADMIN = "admin", "Administrator"

    class Kind(models.TextChoices):
        REGISTRATION = "registration", "Registration"
        PAYMENT_SUCCESS = "payment_success", "Payment successful"
        PAYMENT_FAILED = "payment_failed", "Payment failed"
        ORDER_CONFIRMED = "order_confirmed", "Order confirmed"
        ORDER_STATUS = "order_status", "Order status update"
        SHIPPED = "shipped", "Order shipped"
        DELIVERED = "delivered", "Order delivered"
        NEW_ORDER = "new_order", "New order"
        LOW_STOCK = "low_stock", "Low stock"
        NEW_CUSTOMER = "new_customer", "New customer"

    audience = models.CharField(max_length=10, choices=Audience.choices)
    # Customer notifications target one user; admin notifications use recipient=None
    # and are visible to every dashboard user.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="notifications"
    )
    kind = models.CharField(max_length=30, choices=Kind.choices)
    title = models.CharField(max_length=150)
    message = models.TextField()
    link_url = models.CharField(max_length=300, blank=True)
    dedupe_key = models.CharField(max_length=120)
    is_read = models.BooleanField(default=False)
    email_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["recipient", "is_read", "-created_at"], name="notif_recipient_unread_idx")]
        constraints = [
            models.UniqueConstraint(
                fields=["recipient", "dedupe_key"],
                condition=Q(recipient__isnull=False),
                name="notifications_unique_event_per_recipient",
            ),
            models.UniqueConstraint(
                fields=["dedupe_key"],
                condition=Q(recipient__isnull=True),
                name="notifications_unique_admin_event",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.title}"
