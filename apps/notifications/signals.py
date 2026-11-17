"""Admin alerts raised automatically when data changes, so no view has to remember to do it."""
import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.catalog.models import Inventory

from . import services

log = logging.getLogger(__name__)


@receiver(post_save, sender=Inventory, dispatch_uid="notifications_stock_alert")
def stock_changed(sender, instance, created, **kwargs):
    if created:  # a brand-new variant at zero is not "out of stock"
        return
    try:
        services.sync_stock_alert(instance)
    except Exception:  # noqa: BLE001  (an alert must never break a sale or a stock edit)
        log.exception("Stock alert failed for inventory %s", instance.pk)


@receiver(post_save, sender=get_user_model(), dispatch_uid="notifications_new_customer")
def customer_registered(sender, instance, created, **kwargs):
    if not created or instance.role != "customer":
        return

    def after_commit():
        try:
            services.notify_new_customer(instance)
            services.send_welcome(instance)
        except Exception:  # noqa: BLE001
            log.exception("New-customer notifications failed for user %s", instance.pk)

    transaction.on_commit(after_commit)
