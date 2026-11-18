from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.catalog.models import (
    Brand, Category, Colour, Inventory, Product, ProductImage, ProductVariant, Size, StockAdjustment,
)
from apps.core.forms import StyledFormMixin
from apps.core.validators import validate_image_extension, validate_image_size
from apps.orders.models import DeliveryZone, Order
from apps.promotions.models import DiscountCode, Promotion

from . import rules

User = get_user_model()
DATETIME_LOCAL = "%Y-%m-%dT%H:%M"


class DashForm(StyledFormMixin, forms.Form):
    """Plain form with dashboard styling. Checkbox lists keep their own look."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _tidy(self)


class DashModelForm(StyledFormMixin, forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _tidy(self)


def _tidy(form):
    for field in form.fields.values():
        widget = field.widget
        if isinstance(widget, (forms.CheckboxSelectMultiple, forms.RadioSelect)):
            widget.attrs["class"] = widget.attrs.get("class", "").replace("input", "").strip()
        if isinstance(widget, forms.DateTimeInput):
            widget.input_type = "datetime-local"
            widget.format = DATETIME_LOCAL
            field.input_formats = [DATETIME_LOCAL, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]


def _datetime_field(label, help_text=""):
    return forms.DateTimeField(
        required=False, label=label, help_text=help_text,
        widget=forms.DateTimeInput(format=DATETIME_LOCAL),
    )


# ------------------------------------------------------------------ orders
class OrderStatusForm(DashForm):
    status = forms.ChoiceField(label="Move order to")
    note = forms.CharField(label="Note (optional)", required=False, max_length=255,
                           help_text="Shown to the customer on their order timeline.")
    courier = forms.CharField(label="Courier", required=False, max_length=100)
    tracking_number = forms.CharField(label="Tracking number", required=False, max_length=100)

    def __init__(self, *args, order, **kwargs):
        super().__init__(*args, **kwargs)
        labels = dict(Order.Status.choices)
        self.fields["status"].choices = [(s, labels[s]) for s in rules.next_statuses(order.status)]
        self.fields["courier"].initial = order.courier
        self.fields["tracking_number"].initial = order.tracking_number


class TrackingForm(DashForm):
    courier = forms.CharField(label="Courier", max_length=100)
    tracking_number = forms.CharField(label="Tracking number", max_length=100)

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("auto_id", "id_track_%s")  # the status form on the same page also has courier/tracking fields
        super().__init__(*args, **kwargs)


class RefundForm(DashForm):
    amount = forms.DecimalField(label="Amount to refund (₦)", max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    reason = forms.CharField(label="Reason", max_length=255, help_text="Kept on the order's history and sent to Paystack as a merchant note.")
    restock = forms.BooleanField(label="Return the items to stock", required=False,
                                 help_text="Only applies when the whole payment is refunded.")

    def __init__(self, *args, refundable, **kwargs):
        super().__init__(*args, **kwargs)
        self.refundable = refundable
        self.fields["amount"].initial = refundable
        self.fields["amount"].widget.attrs.update({"max": str(refundable), "step": "0.01"})

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount > self.refundable:
            raise ValidationError(f"At most ₦{self.refundable:,.2f} can still be refunded.")
        return amount


# ------------------------------------------------------------------ inventory
class StockAdjustForm(DashForm):
    REASONS = [
        (StockAdjustment.Reason.RESTOCK, "Restock: add units received"),
        (StockAdjustment.Reason.RETURN, "Customer return: add units back"),
        (StockAdjustment.Reason.DAMAGED, "Damaged or lost: remove units"),
        (StockAdjustment.Reason.CORRECTION, "Stock count: set the counted total"),
    ]
    reason = forms.ChoiceField(choices=REASONS)
    quantity = forms.IntegerField(min_value=0, max_value=100000, label="Quantity",
                                  help_text="Units to add or remove, or the counted total for a stock count.")
    note = forms.CharField(required=False, max_length=255)

    def clean(self):
        data = super().clean()
        if data.get("reason") in (StockAdjustment.Reason.RESTOCK, StockAdjustment.Reason.RETURN, StockAdjustment.Reason.DAMAGED):
            if data.get("quantity") == 0:
                self.add_error("quantity", "Enter at least 1 unit.")
        return data

    def as_service_kwargs(self):
        d = self.cleaned_data
        reason, qty = d["reason"], d["quantity"]
        if reason == StockAdjustment.Reason.CORRECTION:
            return {"set_to": qty, "reason": reason, "note": d["note"]}
        sign = -1 if reason == StockAdjustment.Reason.DAMAGED else 1
        return {"change": sign * qty, "reason": reason, "note": d["note"]}


class ThresholdForm(DashModelForm):
    class Meta:
        model = Inventory
        fields = ["low_stock_threshold"]
        labels = {"low_stock_threshold": "Low-stock alert at or below"}


# ------------------------------------------------------------------ catalogue
class ProductForm(DashModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "category", "brand", "short_description", "description", "keywords",
            "price", "discount_price", "is_featured", "is_new_arrival", "status",
        ]
        widgets = {"description": forms.Textarea(attrs={"rows": 8}), "short_description": forms.TextInput()}
        help_texts = {"status": "Drafts are hidden from the shop."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = Category.objects.select_related("parent").order_by("parent__name", "position", "name")
        self.fields["category"].label_from_instance = lambda c: c.full_path
        self.fields["brand"].queryset = Brand.objects.filter(is_active=True)
        self.fields["brand"].required = False


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        single = super().clean
        files = data if isinstance(data, (list, tuple)) else [data]
        cleaned = [single(f, initial) for f in files if f]
        if not cleaned and self.required:
            raise ValidationError("Choose at least one image.")
        return cleaned


class ProductImagesForm(DashForm):
    images = MultipleImageField(label="Add images", validators=[validate_image_extension, validate_image_size],
                                widget=MultipleFileInput(attrs={"accept": "image/jpeg,image/png,image/webp,image/gif,image/bmp,image/tiff"}))
    colour = forms.ModelChoiceField(queryset=Colour.objects.all(), required=False, empty_label="Any colour",
                                    help_text="Optional: show these images when this colour is picked.")


class ImageAltForm(DashModelForm):
    class Meta:
        model = ProductImage
        fields = ["alt_text", "colour"]


class VariantCreateForm(DashForm):
    sizes = forms.ModelMultipleChoiceField(queryset=Size.objects.all(), widget=forms.CheckboxSelectMultiple)
    colours = forms.ModelMultipleChoiceField(queryset=Colour.objects.all(), widget=forms.CheckboxSelectMultiple)
    price_override = forms.DecimalField(required=False, min_value=Decimal("0.01"), max_digits=12, decimal_places=2,
                                        label="Price override (₦)", help_text="Leave empty to use the product's price.")
    initial_stock = forms.IntegerField(required=False, min_value=0, max_value=100000, initial=0,
                                       label="Opening stock per variant")


class VariantRowForm(DashModelForm):
    class Meta:
        model = ProductVariant
        fields = ["price_override", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Table cells have no visible label, so name each input for screen readers.
        v = self.instance
        who = f"{v.size.name} {v.colour.name}" if v.pk else "variant"
        self.fields["price_override"].widget.attrs["aria-label"] = f"Price override for {who}"
        self.fields["is_active"].widget.attrs["aria-label"] = f"{who} active"


class CategoryForm(DashModelForm):
    class Meta:
        model = Category
        fields = ["parent", "name", "description", "image", "size_guide", "position", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3}), "size_guide": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        parents = Category.objects.filter(parent__isnull=True)  # two levels: collection > type
        if self.instance.pk:
            parents = parents.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = parents
        self.fields["parent"].empty_label = "None: a top-level collection"
        self.fields["parent"].required = False


class BrandForm(DashModelForm):
    class Meta:
        model = Brand
        fields = ["name", "is_active"]


class SizeForm(DashModelForm):
    class Meta:
        model = Size
        fields = ["name", "group", "sort_order"]


class ColourForm(DashModelForm):
    class Meta:
        model = Colour
        fields = ["name", "hex_code", "sort_order"]
        widgets = {"hex_code": forms.TextInput(attrs={"type": "color"})}


# ------------------------------------------------------------------ marketing
class DiscountCodeForm(DashModelForm):
    starts_at = _datetime_field("Starts")
    expires_at = _datetime_field("Expires")

    class Meta:
        model = DiscountCode
        fields = [
            "code", "description", "kind", "percent_off", "amount_off", "minimum_subtotal",
            "starts_at", "expires_at", "usage_limit", "per_user_limit", "is_active",
        ]

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        clash = DiscountCode.objects.filter(code=code).exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError("A code with this name already exists.")
        return code

    def clean(self):
        data = super().clean()
        kind = data.get("kind")
        if kind == DiscountCode.Kind.PERCENTAGE:
            if not data.get("percent_off"):
                self.add_error("percent_off", "Enter the percentage to take off.")
            data["amount_off"] = None
        elif kind == DiscountCode.Kind.FIXED:
            if not data.get("amount_off"):
                self.add_error("amount_off", "Enter the amount to take off.")
            data["percent_off"] = None
        return data


class PromotionForm(DashModelForm):
    starts_at = _datetime_field("Starts")
    ends_at = _datetime_field("Ends")

    class Meta:
        model = Promotion
        fields = ["title", "subtitle", "image", "link_url", "button_text", "position", "starts_at", "ends_at", "is_active"]


class DeliveryZoneForm(DashModelForm):
    class Meta:
        model = DeliveryZone
        fields = ["charge", "free_delivery_threshold", "estimated_days_min", "estimated_days_max", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        state = self.instance.state if self.instance.pk else "this state"
        for name, text in (("charge", "Delivery charge"), ("free_delivery_threshold", "Free delivery from"),
                           ("estimated_days_min", "Minimum days"), ("estimated_days_max", "Maximum days")):
            self.fields[name].widget.attrs["aria-label"] = f"{text}, {state}"

    def clean(self):
        data = super().clean()
        lo, hi = data.get("estimated_days_min"), data.get("estimated_days_max")
        if lo is not None and hi is not None and lo > hi:
            self.add_error("estimated_days_max", "Must be at least the minimum.")
        return data


# ------------------------------------------------------------------ team
class UserAccessForm(DashModelForm):
    class Meta:
        model = User
        fields = ["role", "is_active"]
        labels = {"is_active": "Account active"}


# ------------------------------------------------------------------ website content
from apps.content.models import LookbookSlide, SiteContent, SiteSettings  # noqa: E402

HOME_BLOCKS = {
    "hero": {
        "label": "Hero", "where": "The first screen of the homepage.",
        "fields": {"title": "Headline", "subtitle": "Small line above the headline", "body": "Text under the headline", "image": "Hero image or video"},
        "help": {"title": "Separate lines with a vertical bar, for example: Dressed in|quiet confidence"},
    },
    "intro": {
        "label": "Intro sentence", "where": "The large statement below the hero.",
        "fields": {"title": "Sentence"}, "help": {},
    },
    "editorial": {
        "label": "Brand story", "where": "The editorial section with the large image.",
        "fields": {"subtitle": "Small line above the title", "title": "Title", "body": "Story", "image": "Main image"},
        "help": {"body": "Leave a blank line between paragraphs."},
    },
    "editorial-detail": {
        "label": "Brand story: detail image", "where": "The smaller overlapping image in the brand story.",
        "fields": {"image": "Detail image"}, "help": {},
    },
}


def _image_only(file):
    """Only the hero may be a video; other blocks are plain <img> tags."""
    from apps.core.validators import is_video_name

    if is_video_name(getattr(file, "name", "")):
        raise ValidationError("Only the hero can use a video. Please upload a photo here.")


class HomepageBlockForm(DashModelForm):
    class Meta:
        model = SiteContent
        fields = ["title", "subtitle", "body", "image", "is_published"]
        widgets = {"body": forms.Textarea(attrs={"rows": 7})}
        labels = {"is_published": "Show on the homepage"}

    def __init__(self, *args, key, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = HOME_BLOCKS[key]
        for name in list(self.fields):
            if name == "is_published":
                continue
            if name not in self.config["fields"]:
                del self.fields[name]
                continue
            self.fields[name].label = self.config["fields"][name]
            self.fields[name].help_text = self.config["help"].get(name, "")
        if "title" in self.fields:
            self.fields["title"].required = True
        if "image" in self.fields:
            self.fields["image"].required = False
            if key == "hero":
                self.fields["image"].widget.attrs["accept"] = "image/*,video/mp4,video/webm,video/quicktime"
                self.fields["image"].help_text = "A photo (up to 20 MB) or a short looping video (MP4, WebM or MOV, up to 100 MB)."
            else:
                self.fields["image"].widget.attrs["accept"] = "image/*"
                self.fields["image"].help_text = self.config["help"].get("image", "") or "A photo, up to 20 MB."
                self.fields["image"].validators.append(_image_only)

    def save(self, commit=True):
        if not self.instance.title:  # image-only blocks have no title field; the model still wants one
            self.instance.title = self.config["label"]
        return super().save(commit)


class PageForm(DashModelForm):
    class Meta:
        model = SiteContent
        fields = ["key", "title", "subtitle", "body", "position", "is_published"]
        widgets = {"body": forms.Textarea(attrs={"rows": 16})}
        labels = {"key": "Web address", "is_published": "Published"}
        help_texts = {"key": "Lower-case letters, numbers and hyphens. The page will live at /pages/<this>/ and can't be changed later."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            del self.fields["key"]


class AnnouncementForm(DashModelForm):
    class Meta:
        model = SiteContent
        fields = ["title", "position", "is_published"]
        labels = {"title": "Announcement text", "is_published": "Show in the bar above the header"}
        help_texts = {"position": "If several are published, the lowest number is shown."}
        widgets = {"title": forms.TextInput(attrs={"maxlength": 200})}


class LookbookSlideForm(DashModelForm):
    class Meta:
        model = LookbookSlide
        fields = ["image", "alt_text", "title", "subtitle", "button_text", "product", "link_url",
                  "backdrop", "backdrop_word", "position", "is_active"]
        widgets = {
            "image": forms.ClearableFileInput(attrs={"accept": "image/*"}),
            "backdrop": forms.TextInput(attrs={"type": "color", "style": "width:72px;height:44px;padding:2px"}),
        }
        labels = {"title": "Look name", "subtitle": "Short description"}
        help_texts = {"image": "Best: the full-length model as a transparent PNG or WebP (background removed), standing, "
                               "about 2:3 or 3:4 portrait, up to 20 MB. Ordinary photos work but show as a box.",
                      "title": "Shown large in the panel, for example “The Midnight Puffer”."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.catalog.models import Product

        self.fields["product"].queryset = Product.objects.filter(status=Product.Status.PUBLISHED).order_by("name")
        self.fields["product"].empty_label = "None: use the link below"
        self.fields["button_text"].required = True
        self.fields["backdrop"].required = False       # left out: the model falls back to the default ivory
        self.fields["backdrop"].initial = LookbookSlide._meta.get_field("backdrop").default


class HeroStyleForm(DashModelForm):
    class Meta:
        model = SiteSettings
        fields = ["hero_style"]
        labels = {"hero_style": "Homepage hero"}
        help_texts = {"hero_style": "“Photo or video” uses the Hero block under Homepage. “Lookbook carousel” needs at least 3 active slides; "
                                    "with fewer, the photo or video hero is shown instead."}
        widgets = {"hero_style": forms.RadioSelect}


class SiteSettingsForm(DashModelForm):
    class Meta:
        model = SiteSettings
        exclude = ["updated_at", "hero_style"]
