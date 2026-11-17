import secrets
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q

from apps.core.constants import STATE_CHOICES
from apps.core.models import TimeStampedModel


class DeliveryZone(TimeStampedModel):
    """Administrator-managed delivery charge for one Nigerian state."""

    state = models.CharField(max_length=50, choices=STATE_CHOICES, unique=True)
    charge = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0"))]
    )
    free_delivery_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Optional: orders at or above this subtotal ship free to this state.",
    )
    estimated_days_min = models.PositiveSmallIntegerField(default=2)
    estimated_days_max = models.PositiveSmallIntegerField(default=5)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["state"]

    def __str__(self):
        return f"{self.state} ({self.charge})"

    def charge_for(self, subtotal):
        if self.free_delivery_threshold is not None and subtotal >= self.free_delivery_threshold:
            return Decimal("0.00")
        return self.charge


def generate_order_number():
    """Short, non-sequential, human-readable reference, e.g. AV-7K3Q9XD2."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "AV-" + "".join(secrets.choice(alphabet) for _ in range(8))


class Order(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Pending payment"
        PAID = "paid", "Paid"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    order_number = models.CharField(max_length=20, unique=True, default=generate_order_number, editable=False)
    # Null for guest checkout, or if the account is later deleted (the order is kept).
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING_PAYMENT, db_index=True
    )

    # Customer and delivery details are copied here so history survives profile edits.
    email = models.EmailField()
    customer_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    address_line1 = models.CharField(max_length=255)
    address_line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=50, choices=STATE_CHOICES)
    landmark = models.CharField(max_length=255, blank=True)
    delivery_note = models.CharField(max_length=255, blank=True)

    delivery_zone = models.ForeignKey(
        DeliveryZone, null=True, blank=True, on_delete=models.SET_NULL, related_name="orders"
    )
    delivery_zone_name = models.CharField(max_length=50, blank=True)  # snapshot

    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default=settings.CURRENCY_CODE)

    # Snapshot only; the link to the code itself is promotions.DiscountRedemption.
    discount_code_text = models.CharField(max_length=40, blank=True)

    tracking_number = models.CharField(max_length=100, blank=True)
    courier = models.CharField(max_length=100, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"], name="orders_user_recent_idx"),
            models.Index(fields=["status", "-created_at"], name="orders_status_recent_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(total__gte=0), name="orders_total_non_negative"),
        ]

    def __str__(self):
        return self.order_number

    @property
    def is_paid(self):
        return self.status in {
            self.Status.PAID,
            self.Status.PROCESSING,
            self.Status.SHIPPED,
            self.Status.DELIVERED,
        }


class OrderItem(models.Model):
    """A purchased line. Everything shown to the customer is a snapshot taken at checkout."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    # Kept for reporting; SET_NULL so deleting a variant never erases order history.
    variant = models.ForeignKey(
        "catalog.ProductVariant", null=True, blank=True, on_delete=models.SET_NULL, related_name="order_items"
    )
    product = models.ForeignKey(
        "catalog.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="order_items"
    )

    product_name = models.CharField(max_length=200)
    sku = models.CharField(max_length=64, blank=True)
    size_name = models.CharField(max_length=30)
    colour_name = models.CharField(max_length=50)
    image_url = models.CharField(max_length=500, blank=True)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    line_total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gte=1), name="orderitem_quantity_positive"),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.product_name} ({self.size_name}, {self.colour_name})"


class OrderStatusHistory(models.Model):
    """Audit trail and customer-facing tracking timeline."""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="status_history")
    from_status = models.CharField(max_length=20, choices=Order.Status.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=Order.Status.choices)
    note = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]
        verbose_name_plural = "order status history"

    def __str__(self):
        return f"{self.order.order_number}: {self.from_status or '-'} -> {self.to_status}"
