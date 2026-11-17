from django.conf import settings
from django.db import models

from apps.core.models import TimeStampedModel


class Wishlist(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wishlist"
    )

    def __str__(self):
        return f"Wishlist of {self.user.email}"


class WishlistItem(TimeStampedModel):
    """Saved at product level; the customer picks a variant when moving it to the cart."""

    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "catalog.Product", on_delete=models.CASCADE, related_name="wishlist_items"
    )

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["wishlist", "product"], name="wishlist_unique_product"),
        ]

    def __str__(self):
        return f"{self.product.name} in {self.wishlist}"
