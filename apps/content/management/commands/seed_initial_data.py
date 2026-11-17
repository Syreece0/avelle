"""Idempotent starter data: category tree, sizes, colours, delivery zones, pages.

Run with:  python manage.py seed_initial_data
Everything created here can be edited later from the dashboard.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.catalog.models import Category, Colour, Size
from apps.content.models import SiteContent, SiteSettings
from apps.core.constants import NIGERIAN_STATES
from apps.orders.models import DeliveryZone

CATEGORY_TREE = {
    "Men": ["Shirts", "T-shirts", "Trousers", "Jeans", "Shorts", "Jackets", "Hoodies",
            "Traditional wear", "Shoes", "Accessories"],
    "Women": ["Dresses", "Tops", "Skirts", "Trousers", "Jeans", "Jackets", "Two-piece sets",
              "Traditional wear", "Shoes", "Bags", "Accessories"],
    "Children": ["Boys' clothing", "Girls' clothing", "Baby clothing", "Children's shoes",
                 "Children's accessories"],
}

SIZES = {
    Size.Group.CLOTHING: ["XS", "S", "M", "L", "XL", "XXL"],
    Size.Group.SHOES: [str(n) for n in range(36, 47)],
    Size.Group.CHILDREN: ["2-3Y", "4-5Y", "6-7Y", "8-9Y", "10-11Y", "12-13Y"],
    Size.Group.BABY: ["0-3M", "3-6M", "6-12M", "12-18M"],
    Size.Group.ONE_SIZE: ["One Size"],
}

COLOURS = [
    ("Default", "#CFCFCF"), ("Black", "#111111"), ("White", "#FAFAF7"), ("Ivory", "#F3EBDD"),
    ("Beige", "#D8C3A5"), ("Camel", "#B88A5A"), ("Navy", "#1B2A41"), ("Olive", "#5B6236"),
    ("Burgundy", "#6D1A2B"), ("Red", "#B3261E"), ("Blue", "#2F5D9E"), ("Grey", "#7A7A7A"),
    ("Pink", "#E8A5B5"), ("Green", "#2E6B4F"), ("Gold", "#C9A24B"),
]

PAGES = [
    ("about-us", "About AVELLE"), ("privacy-policy", "Privacy Policy"),
    ("terms-and-conditions", "Terms and Conditions"), ("shipping-information", "Shipping Information"),
    ("returns-and-refunds", "Returns and Refunds"),
]


class Command(BaseCommand):
    help = "Create starter categories, sizes, colours, delivery zones and page stubs."

    @transaction.atomic
    def handle(self, *args, **options):
        for p, (root_name, children) in enumerate(CATEGORY_TREE.items()):
            root, _ = Category.objects.get_or_create(
                parent=None, name=root_name, defaults={"position": p}
            )
            for c, child in enumerate(children):
                Category.objects.get_or_create(parent=root, name=child, defaults={"position": c})

        for group, names in SIZES.items():
            for order, name in enumerate(names):
                Size.objects.get_or_create(group=group, name=name, defaults={"sort_order": order})

        for order, (name, hex_code) in enumerate(COLOURS):
            Colour.objects.get_or_create(name=name, defaults={"hex_code": hex_code, "sort_order": order})

        for state in NIGERIAN_STATES:
            DeliveryZone.objects.get_or_create(
                state=state,
                defaults={"charge": Decimal("2500.00") if state == "Lagos" else Decimal("4500.00")},
            )

        for order, (key, title) in enumerate(PAGES):
            SiteContent.objects.get_or_create(
                key=key, defaults={"title": title, "kind": SiteContent.Kind.PAGE, "position": order}
            )

        SiteSettings.load()
        self.stdout.write(self.style.SUCCESS(
            "Seed complete. Placeholder delivery charges (Lagos 2,500; others 4,500 NGN) "
            "should be reviewed in the dashboard."
        ))
