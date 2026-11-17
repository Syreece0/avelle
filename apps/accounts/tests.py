from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import CustomUser
from apps.notifications.models import Notification


class CustomerNotificationsPage(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(email="a@example.com", password="pw-12345-pw", first_name="A", last_name="B")
        self.other = CustomUser.objects.create_user(email="b@example.com", password="pw-12345-pw", first_name="C", last_name="D")
        mine = dict(audience="customer", recipient=self.user, kind="shipped")
        Notification.objects.create(title="Mine", message="Shipped", dedupe_key="k1", link_url="/orders/AV-1/", **mine)
        Notification.objects.create(title="Evil link", message="x", dedupe_key="k2", link_url="https://evil.example/", **mine)
        Notification.objects.create(title="Theirs", message="secret", dedupe_key="k1", audience="customer", recipient=self.other, kind="shipped")
        Notification.objects.create(title="Admin only", message="x", dedupe_key="k3", audience="admin", kind="new_order")

    def test_requires_login(self):
        response = self.client.get(reverse("accounts:notifications"))
        self.assertEqual(response.status_code, 302)

    def test_shows_only_own_customer_notifications_and_marks_read(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:notifications"))
        self.assertContains(response, "Mine")
        self.assertNotContains(response, "Theirs")
        self.assertNotContains(response, "Admin only")
        self.assertContains(response, 'href="/orders/AV-1/"')
        self.assertNotContains(response, "evil.example")
        self.assertFalse(Notification.objects.filter(recipient=self.user, is_read=False).exists())
        self.assertTrue(Notification.objects.filter(recipient=self.other, is_read=False).exists())
