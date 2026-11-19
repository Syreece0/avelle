import hashlib
import hmac
import json
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.dashboard.tests import make_order, make_user, make_variant
from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.paystack import PaystackError, to_kobo
from apps.payments.services import reconcile_order


def gateway(order, **over):
    data = {"status": "success", "amount": to_kobo(order.total), "currency": "NGN", "channel": "bank_transfer", "id": 6776152813}
    data.update(over)
    return data


def fake_client(result=None, error=None):
    client = mock.Mock()
    if error:
        client.verify.side_effect = error
    else:
        client.verify.return_value = result
    return mock.patch("apps.payments.services.PaystackClient", return_value=client)


class PaidButNeverMarked(TestCase):
    """A customer pays (often by bank transfer) but neither the callback nor the webhook arrives: the order must still catch up."""

    def setUp(self):
        self.order = make_order(Order.Status.PENDING_PAYMENT, variant=make_variant(stock=5), qty=1)
        self.payment = Payment.objects.create(order=self.order, amount=self.order.total)

    def test_reconcile_marks_a_paid_order(self):
        with fake_client(gateway(self.order)):
            self.assertTrue(reconcile_order(self.order))
        self.order.refresh_from_db(); self.payment.refresh_from_db()
        self.assertEqual((self.order.status, self.payment.status, self.payment.channel), ("paid", "success", "bank_transfer"))

    def test_reconcile_picks_the_right_attempt_when_the_customer_clicked_pay_twice(self):
        newer = Payment.objects.create(order=self.order, amount=self.order.total)
        paid_ref = self.payment.reference

        def verify(reference):
            return gateway(self.order) if reference == paid_ref else {"status": "abandoned", "amount": 0, "currency": "NGN"}

        client = mock.Mock(); client.verify.side_effect = verify
        with mock.patch("apps.payments.services.PaystackClient", return_value=client):
            self.assertTrue(reconcile_order(self.order))
        self.payment.refresh_from_db(); newer.refresh_from_db()
        self.assertEqual((self.payment.status, newer.status), ("success", "abandoned"))

    def test_still_unpaid_stays_pending(self):
        with fake_client({"status": "abandoned", "amount": 0, "currency": "NGN"}):
            self.assertFalse(reconcile_order(self.order))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending_payment")

    def test_paystack_down_does_not_crash(self):
        with fake_client(error=PaystackError("down")):
            self.assertFalse(reconcile_order(self.order))

    def test_wrong_amount_is_not_accepted(self):
        with fake_client(gateway(self.order, amount=1)):
            self.assertFalse(reconcile_order(self.order))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending_payment")

    def test_customer_order_page_catches_up_on_its_own(self):
        user = make_user("buyer@example.com", "customer")
        Order.objects.filter(pk=self.order.pk).update(user=user)
        self.client.force_login(user)
        with fake_client(gateway(self.order)):
            response = self.client.get(reverse("orders:detail", args=[self.order.order_number]))
        self.assertEqual(response.status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        self.assertNotContains(response, "Payment not completed")

    def test_customer_check_payment_button(self):
        user = make_user("buyer2@example.com", "customer")
        Order.objects.filter(pk=self.order.pk).update(user=user)
        self.client.force_login(user)
        with fake_client(gateway(self.order)):
            response = self.client.post(reverse("orders:check_payment", args=[self.order.order_number]))
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")

    def test_admin_check_with_paystack_button(self):
        self.client.force_login(make_user("pay-admin@example.com", "admin"))
        with fake_client(gateway(self.order)):
            response = self.client.post(reverse("dashboard:order_check_payment", args=[self.order.order_number]))
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")
        page = self.client.get(reverse("dashboard:order_detail", args=[self.order.order_number]))
        self.assertContains(page, "Successful")

    def test_management_command(self):
        from django.core.management import call_command

        with fake_client(gateway(self.order)):
            call_command("reconcile_payments", stdout=mock.Mock())
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")


@override_settings(PAYSTACK_SECRET_KEY="sk_test_unit")
class Webhook(TestCase):
    def setUp(self):
        self.order = make_order(Order.Status.PENDING_PAYMENT, variant=make_variant(stock=5), qty=1)
        self.payment = Payment.objects.create(order=self.order, amount=self.order.total)
        self.body = json.dumps({"event": "charge.success", "data": {"reference": self.payment.reference}}).encode()

    def post(self, signature=None):
        signature = signature if signature is not None else hmac.new(b"sk_test_unit", self.body, hashlib.sha512).hexdigest()
        return self.client.post(reverse("payments:webhook"), data=self.body, content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE=signature)

    def test_signed_event_marks_the_order_paid(self):
        with fake_client(gateway(self.order)):
            self.assertEqual(self.post().status_code, 200)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "paid")

    def test_bad_signature_is_refused(self):
        self.assertEqual(self.post("deadbeef").status_code, 401)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "pending_payment")
