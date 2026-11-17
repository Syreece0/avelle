"""Demo catalogue so the storefront can be reviewed before real products exist.

    python manage.py seed_demo_catalog            # create (safe to re-run)
    python manage.py seed_demo_catalog --clear    # remove the demo products and demo promotions

Demo products have slugs beginning "demo-" and demo promotions have titles beginning
"Demo:". Images are generated placeholders marked "DEMO IMAGE". Replace them with real
photography from the dashboard; nothing here is used in production.
"""
import random

from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from apps.catalog.models import Brand, Category, Colour, Inventory, Product, ProductImage, ProductVariant, Size, StockAdjustment
from apps.content.models import SiteContent
from apps.core import demo_art, homepage
from apps.promotions.models import Promotion

SIZE_SETS = {
    Size.Group.CLOTHING: ["S", "M", "L", "XL"],
    Size.Group.SHOES: ["40", "41", "42", "43", "44"],
    Size.Group.CHILDREN: ["4-5Y", "6-7Y", "8-9Y"],
    Size.Group.BABY: ["0-3M", "3-6M", "6-12M"],
    Size.Group.ONE_SIZE: ["One Size"],
}

# Tonal backgrounds per root collection (warm, low-contrast)
TONES = {
    "Men": [("#E2D9C9", "#BFB29B"), ("#D9D0C0", "#B3A58D"), ("#E7DFD1", "#C4B8A2")],
    "Women": [("#ECDFD3", "#CDB9A6"), ("#E8DCCB", "#C9B59E"), ("#F0E6DA", "#D4C2AF")],
    "Children": [("#E6E0D0", "#C2BA9F"), ("#EBE4D6", "#CBC3AA"), ("#E1DCCB", "#BDB59B")],
}

# name, root, child, brand, price, discount, kind, size group, colours, featured, new, sold_out
PRODUCTS = [
    ("Linen Camp Shirt", "Men", "Shirts", "Avelle Atelier", 38500, None, "shirt", Size.Group.CLOTHING, ["Ivory", "Olive", "Navy"], True, True, False),
    ("Pleated Wool Trouser", "Men", "Trousers", "Avelle Atelier", 54000, 46000, "trouser", Size.Group.CLOTHING, ["Black", "Grey"], True, False, False),
    ("Waxed Cotton Jacket", "Men", "Jackets", "Avelle Atelier", 98000, None, "jacket", Size.Group.CLOTHING, ["Olive", "Navy"], False, True, False),
    ("Leather Loafer", "Men", "Shoes", "Avelle Atelier", 67500, None, "shoe", Size.Group.SHOES, ["Black", "Camel"], True, True, False),
    ("Silk Slip Dress", "Women", "Dresses", "Maison Ade", 89500, None, "dress", Size.Group.CLOTHING, ["Ivory", "Burgundy", "Black"], True, True, False),
    ("Tailored Wide Trouser", "Women", "Trousers", "Maison Ade", 58000, None, "trouser", Size.Group.CLOTHING, ["Black", "Beige"], False, False, False),
    ("Cotton Ankara Set", "Women", "Two-piece sets", "Avelle Heritage", 46000, 39000, "set", Size.Group.CLOTHING, ["Blue", "Red"], True, False, False),
    ("Structured Tote", "Women", "Bags", "Maison Ade", 72000, None, "bag", Size.Group.ONE_SIZE, ["Black", "Camel", "Ivory"], False, True, False),
    ("Ribbed Knit Top", "Women", "Tops", "Maison Ade", 24500, None, "shirt", Size.Group.CLOTHING, ["Ivory", "Pink"], False, True, False),
    ("Satin Midi Skirt", "Women", "Skirts", "Maison Ade", 36000, None, "skirt", Size.Group.CLOTHING, ["Burgundy", "Black"], True, False, True),
    ("Embroidered Kaftan", "Women", "Traditional wear", "Avelle Heritage", 82000, None, "dress", Size.Group.CLOTHING, ["White", "Gold"], True, False, False),
    ("Boys Oxford Shirt", "Children", "Boys' clothing", "Avelle Junior", 18500, None, "shirt", Size.Group.CHILDREN, ["White", "Blue"], False, True, False),
    ("Girls Smocked Dress", "Children", "Girls' clothing", "Avelle Junior", 22000, 18500, "dress", Size.Group.CHILDREN, ["Pink", "Ivory"], True, False, False),
    ("Baby Knit Romper", "Children", "Baby clothing", "Avelle Junior", 14500, None, "romper", Size.Group.BABY, ["Beige", "White"], True, True, False),
    ("Kids Canvas Cap", "Children", "Children's accessories", "Avelle Junior", 6500, None, "cap", Size.Group.ONE_SIZE, ["Navy", "Green"], False, False, False),
]

DESCRIPTION = (
    "A demonstration product used to review the storefront design. Replace this text, "
    "the images and the price from the dashboard."
)


class Command(BaseCommand):
    help = "Create (or with --clear, remove) demo products, images and promotions."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Remove demo products and demo promotions.")

    def handle(self, *args, **options):
        if options["clear"]:
            return self.clear()
        if not Category.objects.exists():
            self.stdout.write("No categories yet; running seed_initial_data first.")
            call_command("seed_initial_data")
        with transaction.atomic():
            created = self.create_products()
            self.create_content_and_promotions()
        self.stdout.write(self.style.SUCCESS(
            f"Demo catalogue ready: {created} new products. Re-running is safe; remove with --clear."
        ))

    # ------------------------------------------------------------------
    def clear(self):
        products, _ = Product.objects.filter(slug__startswith="demo-").delete()
        promos, _ = Promotion.objects.filter(title__startswith="Demo:").delete()
        self.stdout.write(self.style.SUCCESS(
            f"Removed demo data ({products} product-related rows, {promos} promotion rows). "
            "Category, hero and editorial images were left in place."
        ))

    def create_products(self):
        created = 0
        brands = {}
        for tone_index, row in enumerate(PRODUCTS):
            name, root_name, child_name, brand_name, price, discount, kind, group, colours, featured, new, sold_out = row
            slug = f"demo-{slugify(name)}"
            if Product.objects.filter(slug=slug).exists():
                continue
            root = Category.objects.filter(parent__isnull=True, name=root_name).first()
            category = Category.objects.filter(parent=root, name=child_name).first() if root else None
            if category is None:
                self.stdout.write(self.style.WARNING(f"Skipping {name}: category {root_name} > {child_name} not found."))
                continue
            brand = brands.get(brand_name) or Brand.objects.get_or_create(name=brand_name)[0]
            brands[brand_name] = brand

            product = Product.objects.create(
                name=name, slug=slug, category=category, brand=brand,
                short_description="Demo product", description=DESCRIPTION,
                price=price, discount_price=discount,
                is_featured=featured, is_new_arrival=new, status=Product.Status.PUBLISHED,
            )

            bg, fg = TONES[root_name][tone_index % 3]
            for pose in (0, 1):
                image = ProductImage(product=product, alt_text=name, position=pose, is_primary=(pose == 0))
                data = demo_art.product_image(kind, bg if pose == 0 else fg, fg if pose == 0 else bg, pose=pose)
                image.image.save(f"{slug}-{pose}.jpg", ContentFile(data), save=False)
                image.save()

            rng = random.Random(slug)
            sizes = list(Size.objects.filter(group=group, name__in=SIZE_SETS[group]))
            colour_objs = list(Colour.objects.filter(name__in=colours))
            for size in sizes:
                for colour in colour_objs:
                    variant = ProductVariant.objects.create(product=product, size=size, colour=colour)
                    quantity = 0 if sold_out else rng.choice([0, 2, 4, 8, 12, 20, 30])
                    inventory = Inventory.objects.get(variant=variant)
                    inventory.quantity = quantity
                    inventory.save(update_fields=["quantity", "updated_at"])
                    if quantity:
                        StockAdjustment.objects.create(
                            variant=variant, change=quantity, quantity_after=quantity,
                            reason=StockAdjustment.Reason.RESTOCK, note="Demo seed",
                        )
            created += 1
        return created

    def create_content_and_promotions(self):
        def block(key, defaults):
            obj, _ = SiteContent.objects.get_or_create(
                key=key, defaults={"kind": SiteContent.Kind.HOMEPAGE, **defaults}
            )
            return obj

        def attach(obj, filename, data):
            if not obj.image:
                obj.image.save(filename, ContentFile(data), save=True)

        hero_defaults = homepage.DEFAULTS[homepage.HERO_KEY]
        attach(block(homepage.HERO_KEY, {"title": hero_defaults["title"], "subtitle": hero_defaults["eyebrow"], "body": hero_defaults["body"]}),
               "demo-hero.jpg", demo_art.hero_image())

        block(homepage.INTRO_KEY, {"title": homepage.DEFAULTS[homepage.INTRO_KEY]["title"]})

        ed = homepage.DEFAULTS[homepage.EDITORIAL_KEY]
        attach(block(homepage.EDITORIAL_KEY, {"title": ed["title"], "subtitle": ed["eyebrow"], "body": ed["body"]}),
               "demo-editorial.jpg", demo_art.editorial_image())
        attach(block(homepage.EDITORIAL_DETAIL_KEY, {"title": "Editorial detail"}),
               "demo-editorial-detail.jpg", demo_art.editorial_detail_image())

        collection_art = {"Men": ("shirt", "#D9CFBD", "#E9E1D5"), "Women": ("dress", "#E4D6C6", "#F1E8DC"), "Children": ("romper", "#DFD8C6", "#EEE8D8")}
        for category in Category.objects.filter(parent__isnull=True):
            spec = collection_art.get(category.name)
            if spec and not category.image:
                kind, bg, fg = spec
                category.image.save(f"demo-collection-{category.slug}.jpg", ContentFile(demo_art.collection_image(kind, bg, fg)), save=True)

        if not Promotion.objects.exists():
            for position, (title, subtitle, link, button, bg, fg, kind) in enumerate([
                ("Demo: The season edit", "New pieces for the cooler months", "/shop/?new=1", "Shop new arrivals", "#E9E1D5", "#DCD0BB", "jacket"),
                ("Demo: Selected favourites", "Reduced for a limited time", "/shop/?sale=1", "Shop the edit", "#DDD3C2", "#CFC3AE", "dress"),
            ]):
                promo = Promotion(title=title, subtitle=subtitle, link_url=link, button_text=button, position=position, is_active=True)
                promo.image.save(f"demo-promo-{position}.jpg", ContentFile(demo_art.promo_image(bg, fg, kind)), save=False)
                promo.save()
