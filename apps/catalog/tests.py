from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import STANDARD_COLOUR_NAME, Category, Colour, Product, ProductVariant, Size
from apps.dashboard import services
from apps.dashboard.forms import VariantCreateForm


def make_product(name="Ankara Wrap Dress"):
    return Product.objects.create(name=name, category=Category.objects.create(name=f"Women {name}"), price=Decimal("30000"), status="published")


class OptionalColour(TestCase):
    """A single-colour piece (an Ankara print, say) needs no colour chosen by the admin or the customer."""

    def test_admin_form_accepts_no_colours(self):
        size = Size.objects.create(name="M")
        form = VariantCreateForm({"sizes": [size.pk]})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(list(form.cleaned_data["colours"]), [])

    def test_stand_in_colour_is_not_offered_in_the_picker(self):
        Colour.standard()
        Colour.objects.create(name="Black")
        names = [c.name for c in VariantCreateForm().fields["colours"].queryset]
        self.assertEqual(names, ["Black"])

    def test_standard_colour_is_created_once(self):
        self.assertEqual(Colour.standard().pk, Colour.standard().pk)
        self.assertEqual(Colour.objects.filter(name=STANDARD_COLOUR_NAME).count(), 1)

    def test_label_hides_the_stand_in_but_shows_real_colours(self):
        product, size = make_product(), Size.objects.create(name="M")
        plain = ProductVariant.objects.create(product=product, size=size, colour=Colour.standard())
        black = ProductVariant.objects.create(product=product, size=size, colour=Colour.objects.create(name="Black"))
        self.assertEqual(plain.options_label, "M")
        self.assertEqual(black.options_label, "Black · M")

    def test_product_page_hides_colour_choice_when_there_is_only_one(self):
        product, size = make_product(), Size.objects.create(name="M")
        services.create_variants(product, [size], [Colour.standard()], initial_stock=3)
        response = self.client.get(reverse("catalog:product", args=[product.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-group="colour"')
        self.assertContains(response, 'name="colour"')            # still posted, just not shown
        self.assertNotContains(response, "Standard<")

    def test_product_page_shows_colours_when_there_are_several(self):
        product, size = make_product("Silk Shirt"), Size.objects.create(name="L")
        services.create_variants(product, [size], [Colour.objects.create(name="Black"), Colour.objects.create(name="Ivory")], initial_stock=3)
        response = self.client.get(reverse("catalog:product", args=[product.slug]))
        self.assertContains(response, 'data-group="colour"')

    def test_shop_filter_never_lists_the_stand_in(self):
        product, size = make_product(), Size.objects.create(name="M")
        services.create_variants(product, [size], [Colour.standard()], initial_stock=3)
        self.assertNotContains(self.client.get(reverse("catalog:shop")), 'name="colour"')
