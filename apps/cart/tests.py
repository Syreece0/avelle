from django.test import TestCase
from django.urls import reverse

from apps.cart.models import CartItem
from apps.catalog.models import Inventory
from apps.dashboard.tests import make_variant

AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest", "HTTP_ACCEPT": "application/json"}


class AddToBag(TestCase):
    """The add-to-bag endpoint the product page calls. This path was untested and crashed on PostgreSQL."""

    def setUp(self):
        self.variant = make_variant(stock=5)

    def add(self, quantity=1):
        return self.client.post(reverse("cart:add"), {"variant": self.variant.pk, "quantity": quantity}, **AJAX)

    def test_first_add_creates_a_line(self):
        response = self.add(2)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(CartItem.objects.get().quantity, 2)
        self.assertEqual(response.json()["count"], 2)

    def test_adding_again_increases_quantity(self):
        self.add(1)
        self.add(2)
        self.assertEqual(CartItem.objects.get().quantity, 3)

    def test_quantity_is_capped_at_stock(self):
        response = self.add(9)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CartItem.objects.get().quantity, 5)
        self.assertTrue(response.json()["note"])

    def test_nothing_left_to_add_is_a_clean_error_and_creates_no_empty_line(self):
        self.add(5)
        response = self.add(1)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["ok"])
        self.assertEqual(CartItem.objects.get().quantity, 5)

    def test_sold_out_variant_is_refused(self):
        Inventory.objects.filter(variant=self.variant).update(quantity=0)
        response = self.add(1)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(CartItem.objects.count(), 0)
