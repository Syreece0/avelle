"""Dashboard tests. Run with:  python manage.py test apps.dashboard

NOTE: written without a Django install available, so they have not been executed yet. Treat a failure as
either a bug in the dashboard or a mistake in the test and look at both.
"""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import Category, Colour, Inventory, Product, ProductVariant, Size, StockAdjustment
from apps.orders.models import Order, OrderItem, OrderStatusHistory
from apps.payments.models import Payment, Refund

from . import services
from .services import DashboardError

User = get_user_model()


def make_user(email, role, **kw):
    return User.objects.create_user(email=email, password="pw-12345-pw", first_name="T", last_name=role, role=role, **kw)


def make_variant(stock=10):
    cat = Category.objects.create(name="Men")
    product = Product.objects.create(name="Linen Shirt", category=cat, price=Decimal("20000"), status="published")
    variant = ProductVariant.objects.create(product=product, size=Size.objects.create(name="M"), colour=Colour.objects.create(name="Ivory"))
    if stock:
        services.adjust_stock(variant.pk, change=stock, reason=StockAdjustment.Reason.RESTOCK)
    return variant


def make_order(status=Order.Status.PAID, total="23000", variant=None, qty=2, paid_at=None):
    order = Order.objects.create(
        status=status, email="c@example.com", customer_name="Chi Customer", phone="08012345678", address_line1="1 Road",
        city="Ikeja", state="Lagos", subtotal=Decimal(total) - 3000, delivery_charge=Decimal("3000"), total=Decimal(total),
        paid_at=paid_at or (timezone.now() if status != Order.Status.PENDING_PAYMENT else None),
    )
    if variant:
        OrderItem.objects.create(order=order, variant=variant, product=variant.product, product_name=variant.product.name, sku=variant.sku,
                                 size_name="M", colour_name="Ivory", unit_price=Decimal("10000"), quantity=qty, line_total=Decimal("10000") * qty)
    return order


class AccessTests(TestCase):
    def test_anonymous_is_sent_to_sign_in(self):
        r = self.client.get(reverse("dashboard:overview"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])

    def test_customer_is_forbidden(self):
        make_user("cust@example.com", "customer")
        self.client.login(username="cust@example.com", password="pw-12345-pw")
        self.assertEqual(self.client.get(reverse("dashboard:overview")).status_code, 403)

    def test_roles_are_cumulative(self):
        make_user("staff@example.com", "staff")
        self.client.login(username="staff@example.com", password="pw-12345-pw")
        self.assertEqual(self.client.get(reverse("dashboard:orders")).status_code, 200)
        self.assertEqual(self.client.get(reverse("dashboard:products")).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboard:delivery")).status_code, 403)
        self.client.logout()
        make_user("mgr@example.com", "manager")
        self.client.login(username="mgr@example.com", password="pw-12345-pw")
        self.assertEqual(self.client.get(reverse("dashboard:products")).status_code, 200)

    def test_manager_cannot_refund(self):
        make_user("mgr@example.com", "manager")
        order = make_order()
        self.client.login(username="mgr@example.com", password="pw-12345-pw")
        r = self.client.post(reverse("dashboard:order_refund", args=[order.order_number]), {"amount": "100", "reason": "x"})
        self.assertEqual(r.status_code, 403)

    def test_deactivated_staff_lose_access(self):
        make_user("old@example.com", "admin", is_active=False)
        self.assertFalse(self.client.login(username="old@example.com", password="pw-12345-pw"))

    def test_login_lands_dashboard_users_in_dashboard(self):
        make_user("staff@example.com", "staff")
        r = self.client.post(reverse("accounts:login"), {"username": "staff@example.com", "password": "pw-12345-pw"})
        self.assertRedirects(r, reverse("dashboard:overview"), fetch_redirect_response=False)


class OverviewTests(TestCase):
    def setUp(self):
        make_user("admin@example.com", "admin")
        self.client.login(username="admin@example.com", password="pw-12345-pw")

    def test_empty_database_renders(self):
        self.assertEqual(self.client.get(reverse("dashboard:overview")).status_code, 200)

    def test_revenue_counts_only_collected_sales_in_period(self):
        make_order(Order.Status.PAID, "23000")
        make_order(Order.Status.DELIVERED, "13000")
        make_order(Order.Status.PENDING_PAYMENT, "99000")
        make_order(Order.Status.REFUNDED, "50000")
        make_order(Order.Status.PAID, "70000", paid_at=timezone.now() - timedelta(days=60))
        data = self.client.get(reverse("dashboard:overview")).context["data"]
        revenue = next(c for c in data["cards"] if c["label"] == "Revenue")
        self.assertEqual(revenue["value"], Decimal("36000"))
        self.assertEqual(next(c for c in data["cards"] if c["label"] == "Orders")["value"], 2)
        self.assertEqual(sum(b["value"] for b in data["bars"]), Decimal("36000"))
        self.assertEqual(len(data["bars"]), 30)

    def test_previous_period_comparison(self):
        make_order(Order.Status.PAID, "20000")
        make_order(Order.Status.PAID, "10000", paid_at=timezone.now() - timedelta(days=40))
        data = self.client.get(reverse("dashboard:overview")).context["data"]
        self.assertEqual(next(c for c in data["cards"] if c["label"] == "Revenue")["change"], 100.0)


class StockTests(TestCase):
    def test_adjust_never_goes_below_zero(self):
        v = make_variant(stock=3)
        with self.assertRaises(DashboardError):
            services.adjust_stock(v.pk, change=-4, reason=StockAdjustment.Reason.DAMAGED)
        self.assertEqual(Inventory.objects.get(variant=v).quantity, 3)

    def test_adjust_writes_history_and_set_to(self):
        v = make_variant(stock=3)
        services.adjust_stock(v.pk, set_to=10, reason=StockAdjustment.Reason.CORRECTION, note="count")
        last = StockAdjustment.objects.filter(variant=v).first()
        self.assertEqual((last.change, last.quantity_after), (7, 10))
        with self.assertRaises(DashboardError):
            services.adjust_stock(v.pk, set_to=10, reason=StockAdjustment.Reason.CORRECTION)

    def test_create_variants_skips_existing(self):
        v = make_variant(stock=0)
        s2, c2 = Size.objects.create(name="L"), Colour.objects.create(name="Black")
        created, skipped = services.create_variants(v.product, [v.size, s2], [v.colour, c2], initial_stock=4)
        self.assertEqual((created, skipped), (3, 1))
        self.assertEqual(Inventory.objects.get(variant__product=v.product, variant__size=s2, variant__colour=c2).quantity, 4)


class OrderStatusTests(TestCase):
    def setUp(self):
        self.user = make_user("staff@example.com", "staff")

    def test_happy_path_and_timestamps(self):
        o = make_order()
        services.change_order_status(o.pk, "shipped", user=self.user, courier="GIG", tracking_number="T1")
        o.refresh_from_db()
        self.assertEqual((o.status, o.courier, o.tracking_number), ("shipped", "GIG", "T1"))
        self.assertIsNotNone(o.shipped_at)
        services.change_order_status(o.pk, "delivered", user=self.user)
        o.refresh_from_db()
        self.assertIsNotNone(o.delivered_at)
        self.assertEqual(o.status_history.count(), 2)
        self.assertEqual(o.status_history.first().from_status, "paid")

    def test_illegal_moves_are_refused(self):
        o = make_order()
        for target in ("cancelled", "delivered", "refunded", "pending_payment"):
            with self.assertRaises(DashboardError):
                services.change_order_status(o.pk, target, user=self.user)
        o.refresh_from_db()
        self.assertEqual(o.status, "paid")

    def test_pending_order_can_be_cancelled(self):
        o = make_order(Order.Status.PENDING_PAYMENT)
        services.change_order_status(o.pk, "cancelled", user=self.user)
        o.refresh_from_db()
        self.assertEqual(o.status, "cancelled")
        self.assertIsNotNone(o.cancelled_at)


class RefundTests(TestCase):
    def setUp(self):
        self.admin = make_user("admin@example.com", "admin")
        self.variant = make_variant(stock=10)
        self.order = make_order(variant=self.variant, qty=2, total="23000")
        # what payments.consume_stock would have done when the order was paid
        services.adjust_stock(self.variant.pk, change=-2, reason=StockAdjustment.Reason.SALE, order_number=self.order.order_number)
        self.payment = Payment.objects.create(order=self.order, amount=Decimal("23000"), status=Payment.Status.SUCCESS)

    def _client(self, status="pending"):
        fake = mock.Mock()
        fake.refund.return_value = {"status": status, "id": 555}
        return mock.patch("apps.dashboard.services.client", return_value=fake), fake

    def test_partial_refund_keeps_order_open(self):
        patcher, fake = self._client()
        with patcher:
            refund = services.refund_order(self.order.pk, amount=Decimal("5000"), reason="goodwill", user=self.admin)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        self.assertEqual((refund.status, refund.provider_reference), (Refund.Status.PENDING, "555"))
        fake.refund.assert_called_once()

    def test_cannot_refund_more_than_paid(self):
        patcher, _ = self._client()
        with patcher:
            services.refund_order(self.order.pk, amount=Decimal("20000"), reason="a", user=self.admin)
            with self.assertRaises(DashboardError):
                services.refund_order(self.order.pk, amount=Decimal("3001"), reason="b", user=self.admin)

    def test_full_refund_marks_refunded_and_restocks_exactly_what_was_sold(self):
        patcher, _ = self._client("processed")
        with patcher:
            services.refund_order(self.order.pk, amount=Decimal("23000"), reason="return", user=self.admin, restock=True)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "refunded")
        self.assertEqual(Inventory.objects.get(variant=self.variant).quantity, 10)
        # a second restock must put nothing back
        self.assertEqual(services.restock_order(self.order, self.admin), 0)

    def test_gateway_failure_records_nothing_as_refunded(self):
        from apps.payments.paystack import PaystackError

        fake = mock.Mock()
        fake.refund.side_effect = PaystackError("down")
        with mock.patch("apps.dashboard.services.client", return_value=fake):
            with self.assertRaises(DashboardError):
                services.refund_order(self.order.pk, amount=Decimal("1000"), reason="x", user=self.admin)
        self.assertEqual(Refund.objects.get().status, Refund.Status.FAILED)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        # a failed refund frees the amount again
        patcher, _ = self._client()
        with patcher:
            services.refund_order(self.order.pk, amount=Decimal("23000"), reason="retry", user=self.admin)

    def test_refund_webhook_event_completes_refund(self):
        patcher, _ = self._client()
        with patcher:
            services.refund_order(self.order.pk, amount=Decimal("1000"), reason="x", user=self.admin)
        services.apply_refund_event("refund.processed", {"id": 555})
        self.assertEqual(Refund.objects.get().status, Refund.Status.COMPLETED)


class TeamSafetyTests(TestCase):
    def test_cannot_demote_last_admin_or_self(self):
        admin = make_user("admin@example.com", "admin")
        self.client.login(username="admin@example.com", password="pw-12345-pw")
        r = self.client.post(reverse("dashboard:customer_detail", args=[admin.pk]), {"role": "customer", "is_active": "on"})
        self.assertEqual(r.status_code, 200)  # re-rendered with an error, not saved
        admin.refresh_from_db()
        self.assertEqual(admin.role, "admin")

    def test_admin_can_promote_a_customer(self):
        make_user("admin@example.com", "admin")
        cust = make_user("c@example.com", "customer")
        self.client.login(username="admin@example.com", password="pw-12345-pw")
        self.client.post(reverse("dashboard:customer_detail", args=[cust.pk]), {"role": "staff", "is_active": "on"})
        cust.refresh_from_db()
        self.assertEqual(cust.role, "staff")


# =============================================================== Phase 10
from django.core import mail  # noqa: E402

from apps.content.models import SiteContent  # noqa: E402
from apps.notifications import services as notify  # noqa: E402
from apps.notifications.models import Notification  # noqa: E402
from apps.orders.expiry import expire_unpaid  # noqa: E402
from apps.payments.paystack import PaystackError  # noqa: E402


class StockAlertTests(TestCase):
    def test_low_then_out_then_restock_clears_and_can_refire(self):
        v = make_variant(stock=20)  # default threshold is 5
        self.assertFalse(Notification.objects.filter(kind="low_stock").exists())
        services.adjust_stock(v.pk, change=-16, reason=StockAdjustment.Reason.DAMAGED)  # 4 left: low
        self.assertEqual(Notification.objects.filter(dedupe_key=f"stock-low:{v.pk}").count(), 1)
        services.adjust_stock(v.pk, change=-1, reason=StockAdjustment.Reason.DAMAGED)  # 3 left: same alert, not a second one
        self.assertEqual(Notification.objects.filter(kind="low_stock").count(), 1)
        services.adjust_stock(v.pk, change=-3, reason=StockAdjustment.Reason.DAMAGED)  # out: low replaced by out
        self.assertEqual(list(Notification.objects.filter(kind="low_stock").values_list("dedupe_key", flat=True)), [f"stock-out:{v.pk}"])
        services.adjust_stock(v.pk, change=30, reason=StockAdjustment.Reason.RESTOCK)  # healthy: cleared
        self.assertFalse(Notification.objects.filter(kind="low_stock").exists())
        services.adjust_stock(v.pk, change=-28, reason=StockAdjustment.Reason.DAMAGED)  # low again: fires again
        self.assertEqual(Notification.objects.filter(kind="low_stock").count(), 1)

    def test_new_variant_at_zero_is_not_an_alert(self):
        make_variant(stock=0)
        self.assertFalse(Notification.objects.filter(kind="low_stock").exists())


class CustomerEmailTests(TestCase):
    def setUp(self):
        self.staff = make_user("staff@example.com", "staff")

    def test_shipped_email_sent_once_with_tracking(self):
        o = make_order()
        with self.captureOnCommitCallbacks(execute=True):
            services.change_order_status(o.pk, "shipped", user=self.staff, courier="GIG", tracking_number="T123")
        shipped = [m for m in mail.outbox if "shipped" in m.subject]
        self.assertEqual(len(shipped), 1)
        self.assertIn("T123", shipped[0].body)
        self.assertEqual(shipped[0].to, ["c@example.com"])
        o.refresh_from_db()
        notify.notify_order_status(o)  # a retry must not send again
        self.assertEqual(len([m for m in mail.outbox if "shipped" in m.subject]), 1)

    def test_email_failure_does_not_block_status_change_and_can_retry(self):
        o = make_order()
        with mock.patch("apps.notifications.services.send_mail", side_effect=OSError("smtp down")):
            with self.captureOnCommitCallbacks(execute=True):
                services.change_order_status(o.pk, "shipped", user=self.staff)
        o.refresh_from_db()
        self.assertEqual(o.status, "shipped")
        self.assertFalse(Notification.objects.filter(dedupe_key__startswith="order-email:shipped").exists())
        notify.notify_order_status(o)
        self.assertEqual(len([m for m in mail.outbox if "shipped" in m.subject]), 1)

    def test_processing_sends_nothing(self):
        o = make_order()
        with self.captureOnCommitCallbacks(execute=True):
            services.change_order_status(o.pk, "processing", user=self.staff)
        self.assertEqual(mail.outbox, [])

    def test_bookkeeping_rows_hidden_from_notification_list(self):
        o = make_order()
        with self.captureOnCommitCallbacks(execute=True):
            services.change_order_status(o.pk, "shipped", user=self.staff)
        self.assertTrue(Notification.objects.filter(dedupe_key__startswith="order-email:").exists())
        self.assertFalse(notify.visible_admin().filter(dedupe_key__startswith="order-email:").exists())

    def test_registration_creates_admin_alert_and_welcome_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            make_user("new@example.com", "customer")
        self.assertTrue(Notification.objects.filter(kind="new_customer").exists())
        self.assertTrue(any(m.subject == "Welcome to AVELLE" for m in mail.outbox))
        with self.captureOnCommitCallbacks(execute=True):
            make_user("team@example.com", "staff")
        self.assertEqual(Notification.objects.filter(kind="new_customer").count(), 1)


class NotificationViewTests(TestCase):
    def setUp(self):
        make_user("staff@example.com", "staff")
        self.client.login(username="staff@example.com", password="pw-12345-pw")
        self.n = Notification.objects.create(audience="admin", kind="new_order", title="New order", message="m", dedupe_key="new-order:X", link_url="/dashboard/orders/X/")

    def test_list_and_mark_read(self):
        self.assertContains(self.client.get(reverse("dashboard:notifications")), "New order")
        r = self.client.post(reverse("dashboard:notification_read", args=[self.n.pk]), {"open": "1"})
        self.assertRedirects(r, "/dashboard/orders/X/", fetch_redirect_response=False)
        self.n.refresh_from_db()
        self.assertTrue(self.n.is_read)

    def test_open_never_redirects_off_site(self):
        self.n.link_url = "https://evil.example/"
        self.n.save()
        r = self.client.post(reverse("dashboard:notification_read", args=[self.n.pk]), {"open": "1"})
        self.assertRedirects(r, reverse("dashboard:notifications"), fetch_redirect_response=False)

    def test_mark_all_read(self):
        self.client.post(reverse("dashboard:notifications_read_all"))
        self.assertEqual(notify.admin_unread_count(), 0)


class ReportTests(TestCase):
    def setUp(self):
        make_user("mgr@example.com", "manager")
        self.client.login(username="mgr@example.com", password="pw-12345-pw")
        self.v = make_variant(stock=9)

    def test_staff_cannot_open_reports(self):
        self.client.logout()
        make_user("staff@example.com", "staff")
        self.client.login(username="staff@example.com", password="pw-12345-pw")
        self.assertEqual(self.client.get(reverse("dashboard:reports")).status_code, 403)

    def test_sales_report_matches_orders_and_excludes_refunded_and_unpaid(self):
        make_order(variant=self.v, total="23000")
        make_order(Order.Status.REFUNDED, "50000")
        make_order(Order.Status.PENDING_PAYMENT, "40000")
        data = self.client.get(reverse("dashboard:reports")).context["data"]
        self.assertEqual(data["summary"][0][1], Decimal("23000"))
        self.assertEqual(len(data["rows"]), 1)

    def test_csv_export_is_formula_safe_and_complete(self):
        o = make_order(variant=self.v)
        o.customer_name = "=cmd|' /C calc'!A0"
        o.save()
        r = self.client.get(reverse("dashboard:reports") + "?report=sales&export=csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        text = r.content.decode("utf-8-sig")
        self.assertIn("'=cmd", text)
        self.assertNotIn(",=cmd", text)
        self.assertEqual(len(text.strip().splitlines()), 2)

    def test_stock_report_values_stock_and_ignores_range(self):
        data = self.client.get(reverse("dashboard:reports") + "?report=stock&from=garbage").context["data"]
        self.assertEqual(data["summary"][1][1], 9)
        self.assertEqual(data["summary"][2][1], Decimal("180000"))

    def test_bad_dates_do_not_crash(self):
        self.assertEqual(self.client.get(reverse("dashboard:reports") + "?from=nope&to=2999-01-01&report=zzz").status_code, 200)


class ContentTests(TestCase):
    def setUp(self):
        make_user("mgr@example.com", "manager")
        self.client.login(username="mgr@example.com", password="pw-12345-pw")

    def test_hero_saves_and_requires_headline(self):
        url = reverse("dashboard:content_homepage_edit", args=["hero"])
        self.assertEqual(self.client.post(url, {"title": "", "is_published": "on"}).status_code, 200)
        self.assertFalse(SiteContent.objects.filter(key="hero").exists())
        self.client.post(url, {"title": "Dressed in|quiet confidence", "subtitle": "New", "body": "Text", "is_published": "on"})
        hero = SiteContent.objects.get(key="hero")
        self.assertEqual((hero.kind, hero.title), ("homepage", "Dressed in|quiet confidence"))

    def test_unknown_block_key_is_ignored(self):
        self.client.get(reverse("dashboard:content_homepage_edit", args=["nope"]))
        self.assertFalse(SiteContent.objects.filter(key="nope").exists())

    def test_page_create_edit_delete(self):
        self.client.post(reverse("dashboard:content_page_new"), {"key": "about-us", "title": "About us", "body": "Hi", "position": 0, "is_published": "on"})
        page = SiteContent.objects.get(key="about-us")
        self.assertEqual(self.client.get("/pages/about-us/").status_code, 200)
        self.client.post(reverse("dashboard:content_page_edit", args=[page.pk]), {"title": "About AVELLE", "body": "Hi", "position": 0, "is_published": "on", "key": "hacked"})
        page.refresh_from_db()
        self.assertEqual((page.key, page.title), ("about-us", "About AVELLE"))
        self.client.post(reverse("dashboard:content_page_delete", args=[page.pk]))
        self.assertFalse(SiteContent.objects.filter(pk=page.pk).exists())

    def test_announcement_shows_on_storefront(self):
        self.client.post(reverse("dashboard:content_announcement_new"), {"title": "Free delivery over ₦50,000", "position": 0, "is_published": "on"})
        self.assertContains(self.client.get("/"), "Free delivery over")

    def test_site_settings_save(self):
        r = self.client.post(reverse("dashboard:content_settings"), {"store_name": "AVELLE", "tagline": "", "contact_email": "hello@avelle.test", "contact_phone": "", "whatsapp_number": "", "address": "", "instagram_url": "", "facebook_url": "", "tiktok_url": "", "x_url": ""})
        self.assertEqual(r.status_code, 302)

    def test_newsletter_export(self):
        from apps.content.models import NewsletterSubscriber

        NewsletterSubscriber.objects.create(email="a@example.com")
        r = self.client.get(reverse("dashboard:newsletter") + "?export=csv")
        self.assertIn("a@example.com", r.content.decode("utf-8-sig"))


class ExpiryTests(TestCase):
    def _old(self, hours):
        o = make_order(Order.Status.PENDING_PAYMENT)
        Order.objects.filter(pk=o.pk).update(created_at=timezone.now() - timedelta(hours=hours))
        return o

    def test_old_unpaid_orders_cancelled_recent_kept(self):
        old, fresh = self._old(72), self._old(2)
        r = expire_unpaid(hours=48)
        old.refresh_from_db(); fresh.refresh_from_db()
        self.assertEqual((old.status, fresh.status, r["cancelled"]), ("cancelled", "pending_payment", 1))
        self.assertTrue(OrderStatusHistory.objects.filter(order=old, note__startswith="Expired").exists())

    def test_paid_orders_never_touched(self):
        o = make_order(Order.Status.PAID)
        Order.objects.filter(pk=o.pk).update(created_at=timezone.now() - timedelta(days=30))
        expire_unpaid(hours=48)
        o.refresh_from_db()
        self.assertEqual(o.status, "paid")

    def test_paystack_unreachable_leaves_order_alone(self):
        o = self._old(72)
        Payment.objects.create(order=o, amount=o.total)
        with mock.patch("apps.orders.expiry.verify_reference", side_effect=PaystackError("down")):
            r = expire_unpaid(hours=48)
        o.refresh_from_db()
        self.assertEqual((o.status, r["skipped"]), ("pending_payment", 1))

    def test_customer_who_actually_paid_is_not_cancelled(self):
        o = self._old(72)
        p = Payment.objects.create(order=o, amount=o.total)

        def fake_verify(ref):
            Order.objects.filter(pk=o.pk).update(status="paid")
            return p

        with mock.patch("apps.orders.expiry.verify_reference", side_effect=fake_verify):
            r = expire_unpaid(hours=48)
        o.refresh_from_db()
        self.assertEqual((o.status, r["rescued"], r["cancelled"]), ("paid", 1, 0))

    def test_dry_run_changes_nothing(self):
        o = self._old(72)
        r = expire_unpaid(hours=48, dry_run=True)
        o.refresh_from_db()
        self.assertEqual((o.status, r["cancelled"]), ("pending_payment", 1))


class EveryDashboardPageRenders(TestCase):
    """Smoke test: each sidebar page opens for an administrator without an error (catches broken URL names)."""

    def test_sidebar_pages_render(self):
        admin = make_user("smoke-admin@example.com", "admin")
        self.client.force_login(admin)
        from apps.dashboard import access

        for item in access.nav_items(admin):
            response = self.client.get(item["url"])
            self.assertEqual(response.status_code, 200, item["url"])
        for name in ("content_pages", "content_announcements", "content_settings"):
            self.assertEqual(self.client.get(reverse(f"dashboard:{name}")).status_code, 200, name)
