from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Inventory, ProductVariant


@receiver(post_save, sender=ProductVariant)
def create_inventory_for_variant(sender, instance, created, **kwargs):
    """Every variant gets exactly one Inventory row, starting at zero stock."""
    if created:
        Inventory.objects.get_or_create(variant=instance)
