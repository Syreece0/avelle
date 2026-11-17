from django.core.management.base import BaseCommand

from apps.orders.expiry import expire_unpaid


class Command(BaseCommand):
    help = "Cancel orders that were never paid (checks Paystack first). Run it daily, e.g. as a Render cron job."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=48, help="Cancel unpaid orders older than this (default 48).")
        parser.add_argument("--dry-run", action="store_true", help="Report what would happen without changing anything.")

    def handle(self, *args, **opts):
        if opts["hours"] < 1:
            self.stderr.write("--hours must be at least 1.")
            return
        r = expire_unpaid(hours=opts["hours"], dry_run=opts["dry_run"])
        prefix = "Would cancel" if opts["dry_run"] else "Cancelled"
        self.stdout.write(self.style.SUCCESS(f"{prefix} {r['cancelled']}; paid after all {r['rescued']}; skipped (Paystack unreachable) {r['skipped']}; checked {r['checked']}."))
