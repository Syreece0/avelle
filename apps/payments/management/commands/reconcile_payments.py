"""Ask Paystack about every unpaid order from the last few days and mark the ones that were actually paid.

Safety net for missed callbacks/webhooks. Safe to run as often as you like (it is idempotent):
    python manage.py reconcile_payments            # last 3 days
    python manage.py reconcile_payments --days 14
On Render this can run as a cron job every 10-15 minutes.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.orders.models import Order
from apps.payments.services import reconcile_order


class Command(BaseCommand):
    help = "Mark unpaid orders as paid when Paystack says they were."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=3)

    def handle(self, *args, **options):
        since = timezone.now() - timedelta(days=options["days"])
        orders = Order.objects.filter(status=Order.Status.PENDING_PAYMENT, created_at__gte=since, payments__pk__isnull=False).distinct()
        fixed = checked = 0
        for order in orders:
            checked += 1
            if reconcile_order(order):
                fixed += 1
                self.stdout.write(f"Marked {order.order_number} as paid")
        self.stdout.write(self.style.SUCCESS(f"Checked {checked} unpaid order(s); {fixed} had been paid."))
