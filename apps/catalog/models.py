from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

from apps.core.models import TimeStampedModel
from apps.core.utils import unique_slugify
from apps.core.validators import validate_image_extension, validate_image_size

MAX_CATEGORY_DEPTH = 3  # e.g. Men > Shirts > Formal shirts


class Category(TimeStampedModel):
    """Database-driven category tree.

    Top-level rows are the main collections (Men, Women, Children). Child rows
    are subcategories / clothing types (Shirts, Dresses, Baby clothing ...).
    Administrators can add or move nodes without touching code.
    """

    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(
        upload_to="categories/",
        blank=True,
        validators=[validate_image_extension, validate_image_size],
    )
    size_guide = models.TextField(
        blank=True,
        help_text="Shown on product pages. Subcategories inherit their parent's guide if left empty.",
    )
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["position", "name"]
        verbose_name_plural = "categories"
        constraints = [
            # Slugs are unique among siblings: /men/trousers and /women/trousers can coexist.
            models.UniqueConstraint(
                fields=["parent", "slug"], name="catalog_category_unique_slug_per_parent"
            ),
            models.UniqueConstraint(
                fields=["slug"],
                condition=Q(parent__isnull=True),
                name="catalog_category_unique_root_slug",
            ),
        ]

    def __str__(self):
        return self.full_path

    @property
    def depth(self):
        depth, node = 1, self.parent
        while node is not None:
            depth += 1
            node = node.parent
        return depth

    @property
    def full_path(self):
        names, node = [self.name], self.parent
        while node is not None:
            names.append(node.name)
            node = node.parent
        return " > ".join(reversed(names))

    @property
    def is_root(self):
        return self.parent_id is None

    def get_root(self):
        node = self
        while node.parent is not None:
            node = node.parent
        return node

    def get_descendant_ids(self, include_self=True):
        """IDs of this category and everything beneath it (for filtering)."""
        ids = [self.pk] if include_self else []
        frontier = [self.pk]
        while frontier:
            frontier = list(
                Category.objects.filter(parent_id__in=frontier).values_list("pk", flat=True)
            )
            ids.extend(frontier)
        return ids

    def get_size_guide(self):
        node = self
        while node is not None:
            if node.size_guide.strip():
                return node.size_guide
            node = node.parent
        return ""

    def clean(self):
        if self.parent_id:
            if self.pk and self.parent_id == self.pk:
                raise ValidationError({"parent": "A category cannot be its own parent."})
            node = self.parent
            while node is not None:
                if self.pk and node.pk == self.pk:
                    raise ValidationError({"parent": "A category cannot sit beneath its own descendant."})
                node = node.parent
            if self.parent.depth >= MAX_CATEGORY_DEPTH:
                raise ValidationError(
                    {"parent": f"Categories can be nested at most {MAX_CATEGORY_DEPTH} levels deep."}
                )

    def save(self, *args, **kwargs):
        if not self.slug:
            siblings = Category.objects.filter(parent_id=self.parent_id)
            self.slug = unique_slugify(self, self.name, queryset=siblings)
        super().save(*args, **kwargs)


class Brand(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        super().save(*args, **kwargs)


class Size(models.Model):
    class Group(models.TextChoices):
        CLOTHING = "clothing", "Clothing"
        SHOES = "shoes", "Shoes"
        CHILDREN = "children", "Children"
        BABY = "baby", "Baby"
        ONE_SIZE = "one_size", "One size"

    name = models.CharField(max_length=30, help_text="For example: M, 42, 6-12M, One Size")
    group = models.CharField(max_length=20, choices=Group.choices, default=Group.CLOTHING)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["group", "sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["group", "name"], name="catalog_size_unique_name_per_group"),
        ]

    def __str__(self):
        return self.name


STANDARD_COLOUR_NAME = "Standard"


class Colour(models.Model):
    """A product colour. "Standard" is the built-in stand-in for pieces that come in one colour only
    (an Ankara print, say): customers are never asked to choose it and it is not shown to them."""

    name = models.CharField(max_length=50, unique=True)
    hex_code = models.CharField(
        max_length=7,
        default="#000000",
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Enter a hex colour such as #1A1A1A.")],
    )
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    @classmethod
    def standard(cls):
        return cls.objects.get_or_create(name=STANDARD_COLOUR_NAME, defaults={"hex_code": "#CFC6B6", "sort_order": 9999})[0]

    @property
    def is_standard(self):
        return self.name == STANDARD_COLOUR_NAME


class ProductQuerySet(models.QuerySet):
    def published(self):
        return self.filter(status=Product.Status.PUBLISHED)

    def in_stock(self):
        return self.filter(
            variants__is_active=True, variants__inventory__quantity__gt=0
        ).distinct()

    def discounted(self):
        return self.filter(discount_price__isnull=False)


class Product(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    brand = models.ForeignKey(
        Brand, null=True, blank=True, on_delete=models.SET_NULL, related_name="products"
    )
    short_description = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    keywords = models.CharField(
        max_length=300, blank=True, help_text="Extra search terms, separated by spaces."
    )

    # Prices are in NGN.
    price = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    discount_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    is_featured = models.BooleanField(default=False)
    is_new_arrival = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="catalog_prod_status_new_idx"),
            models.Index(fields=["category", "status"], name="catalog_prod_cat_status_idx"),
            models.Index(fields=["is_featured", "status"], name="catalog_prod_featured_idx"),
            models.Index(fields=["is_new_arrival", "status"], name="catalog_prod_newarr_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(discount_price__isnull=True) | Q(discount_price__lt=F("price")),
                name="catalog_product_discount_below_price",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.discount_price is not None and self.price is not None:
            if self.discount_price >= self.price:
                raise ValidationError(
                    {"discount_price": "The discounted price must be lower than the regular price."}
                )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name)
        if self.status == self.Status.PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        # Matches the product-detail route added in Phase 5.
        return f"/shop/products/{self.slug}/"

    @property
    def primary_image(self):
        """Primary image (falls back to the first). Uses prefetched images when present."""
        images = list(self.images.all())
        for image in images:
            if image.is_primary:
                return image
        return images[0] if images else None

    @property
    def current_price(self):
        return self.discount_price if self.discount_price is not None else self.price

    @property
    def has_discount(self):
        return self.discount_price is not None

    @property
    def discount_percent(self):
        if not self.has_discount:
            return 0
        return int(((self.price - self.discount_price) / self.price * 100).quantize(Decimal("1")))


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(
        upload_to="products/%Y/%m/", validators=[validate_image_extension, validate_image_size]
    )
    alt_text = models.CharField(max_length=200, blank=True)
    colour = models.ForeignKey(
        Colour,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="product_images",
        help_text="Optional: show this image when the customer picks this colour.",
    )
    position = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)

    class Meta:
        ordering = ["-is_primary", "position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_primary=True),
                name="catalog_one_primary_image_per_product",
            ),
        ]

    def __str__(self):
        return f"{self.product.name} image {self.position}"


class ProductVariant(TimeStampedModel):
    """One sellable combination of product + size + colour."""

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    size = models.ForeignKey(Size, on_delete=models.PROTECT, related_name="variants")
    colour = models.ForeignKey(Colour, on_delete=models.PROTECT, related_name="variants")
    sku = models.CharField(max_length=64, unique=True, blank=True)
    price_override = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Leave empty to use the product's price.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["product", "size__sort_order", "colour__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "size", "colour"], name="catalog_variant_unique_combination"
            ),
        ]

    def __str__(self):
        return f"{self.product.name} / {self.size.name} / {self.colour.name}"

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = f"AV{self.product_id:06d}-{self.size_id}-{self.colour_id}"
        super().save(*args, **kwargs)

    @property
    def options_label(self):
        """What a customer should see for this variant: the colour only if there is a real choice of colours."""
        parts = [] if self.colour.is_standard else [self.colour.name]
        parts.append(self.size.name)
        return " · ".join(parts)

    @property
    def unit_price(self):
        if self.price_override is not None:
            return self.price_override
        return self.product.current_price


class Inventory(TimeStampedModel):
    """Stock level for exactly one variant (created automatically with it)."""

    variant = models.OneToOneField(
        ProductVariant, on_delete=models.CASCADE, related_name="inventory"
    )
    quantity = models.PositiveIntegerField(default=0)  # DB-level guard: never negative
    low_stock_threshold = models.PositiveIntegerField(
        default=settings.LOW_STOCK_DEFAULT_THRESHOLD
    )

    class Meta:
        verbose_name_plural = "inventory"

    def __str__(self):
        return f"{self.variant} ({self.quantity} in stock)"

    @property
    def is_in_stock(self):
        return self.quantity > 0

    @property
    def is_low_stock(self):
        return 0 < self.quantity <= self.low_stock_threshold


class StockAdjustment(models.Model):
    """Append-only stock history. Every change to Inventory writes a row here."""

    class Reason(models.TextChoices):
        RESTOCK = "restock", "Restock"
        SALE = "sale", "Sale"
        CANCELLATION = "cancellation", "Order cancelled"
        RETURN = "return", "Customer return"
        CORRECTION = "correction", "Stock count correction"
        DAMAGED = "damaged", "Damaged or lost"

    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name="stock_adjustments"
    )
    change = models.IntegerField(help_text="Positive adds stock, negative removes it.")
    quantity_after = models.PositiveIntegerField()
    reason = models.CharField(max_length=20, choices=Reason.choices)
    note = models.CharField(max_length=255, blank=True)
    # Plain reference (not a FK) so catalog never depends on orders.
    order_number = models.CharField(max_length=20, blank=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["variant", "-created_at"], name="catalog_stockadj_variant_idx")]

    def __str__(self):
        return f"{self.variant} {self.change:+d} ({self.get_reason_display()})"


class Review(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="reviews")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=120, blank=True)
    body = models.TextField(blank=True)
    is_verified_purchase = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False, help_text="Only approved reviews are public.")

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["product", "user"], name="catalog_one_review_per_user_product"),
            models.CheckConstraint(
                condition=Q(rating__gte=1) & Q(rating__lte=5), name="catalog_review_rating_1_to_5"
            ),
        ]

    def __str__(self):
        return f"{self.rating}/5 for {self.product.name} by {self.user.email}"
