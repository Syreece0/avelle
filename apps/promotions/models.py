from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.validators import validate_image_extension, validate_image_size


class Promotion(TimeStampedModel):
    """A promotional banner (homepage Section G)."""

    title = models.CharField(max_length=150)
    subtitle = models.CharField(max_length=255, blank=True)
    image = models.ImageField(
        upload_to="promotions/", validators=[validate_image_extension, validate_image_size]
    )
    link_url = models.CharField(max_length=300, blank=True, help_text="Where the banner leads, e.g. /shop/?sale=1")
    button_text = models.CharField(max_length=40, blank=True)
    position = models.PositiveIntegerField(default=0)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "-created_at"]

    def __str__(self):
        return self.title

    def clean(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "The end date must be after the start date."})

    @property
    def is_live(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True


class DiscountCode(TimeStampedModel):
    class Kind(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed amount"

    code = models.CharField(max_length=40, unique=True, help_text="Stored in upper case.")
    description = models.CharField(max_length=200, blank=True)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    percent_off = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(100)]
    )
    amount_off = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(Decimal("0.01"))]
    )
    minimum_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    starts_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    usage_limit = models.PositiveIntegerField(null=True, blank=True, help_text="Total redemptions allowed.")
    per_user_limit = models.PositiveIntegerField(default=1, help_text="Redemptions allowed per customer.")
    times_used = models.PositiveIntegerField(default=0, editable=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # A percentage code needs percent_off; a fixed code needs amount_off.
            models.CheckConstraint(
                condition=(
                    Q(kind="percentage", percent_off__isnull=False, amount_off__isnull=True)
                    | Q(kind="fixed", amount_off__isnull=False, percent_off__isnull=True)
                ),
                name="promotions_code_value_matches_kind",
            ),
        ]

    def __str__(self):
        return self.code

    def clean(self):
        if self.kind == self.Kind.PERCENTAGE and not self.percent_off:
            raise ValidationError({"percent_off": "Enter the percentage to take off."})
        if self.kind == self.Kind.FIXED and not self.amount_off:
            raise ValidationError({"amount_off": "Enter the amount to take off."})
        if self.starts_at and self.expires_at and self.expires_at <= self.starts_at:
            raise ValidationError({"expires_at": "The expiry must be after the start date."})

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        # Keep exactly one value field populated so the DB constraint holds.
        if self.kind == self.Kind.PERCENTAGE:
            self.amount_off = None
        elif self.kind == self.Kind.FIXED:
            self.percent_off = None
        super().save(*args, **kwargs)

    def discount_for(self, subtotal):
        """Discount amount for ``subtotal`` (never more than the subtotal itself)."""
        if self.kind == self.Kind.PERCENTAGE:
            amount = (subtotal * Decimal(self.percent_off) / Decimal(100)).quantize(Decimal("0.01"))
        else:
            amount = self.amount_off
        return min(amount, subtotal)


class DiscountRedemption(models.Model):
    """One use of a code on one order. Powers per-user limits and prevents double counting."""

    code = models.ForeignKey(DiscountCode, on_delete=models.CASCADE, related_name="redemptions")
    order = models.OneToOneField("orders.Order", on_delete=models.CASCADE, related_name="discount_redemption")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    email = models.EmailField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.code.code} on {self.order.order_number}"
