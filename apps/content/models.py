from django.db import models
from django.core.validators import RegexValidator

from apps.core.models import TimeStampedModel
from apps.core.storage import homepage_media_storage
from apps.core.validators import is_video_name, validate_image_extension, validate_image_size, validate_media_extension, validate_media_size


class SiteContent(TimeStampedModel):
    """An admin-editable piece of public content, addressed by a fixed ``key``.

    Covers legal and information pages (about, privacy, terms, shipping,
    returns), homepage hero/editorial copy, and newsletter announcements. The
    set of keys is open: administrators can add new blocks without code.
    """

    class Kind(models.TextChoices):
        PAGE = "page", "Page"
        HOMEPAGE = "homepage", "Homepage block"
        ANNOUNCEMENT = "announcement", "Announcement"

    key = models.SlugField(max_length=80, unique=True, help_text="Stable identifier used by templates, e.g. privacy-policy")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.PAGE)
    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True)
    body = models.TextField(blank=True)
    # Despite the name this may be a video (homepage hero). See apps.core.storage.
    image = models.FileField(
        upload_to="content/", blank=True, storage=homepage_media_storage,
        validators=[validate_media_extension, validate_media_size],
    )
    position = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "position", "key"]

    @property
    def is_video(self):
        return bool(self.image) and is_video_name(self.image.name)

    def __str__(self):
        return f"{self.title} [{self.key}]"


class SiteSettings(models.Model):
    """Singleton: store-wide contact details and social links (footer, contact page)."""

    store_name = models.CharField(max_length=100, default="AVELLE")
    tagline = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    whatsapp_number = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=300, blank=True)
    instagram_url = models.URLField(blank=True)
    facebook_url = models.URLField(blank=True)
    tiktok_url = models.URLField(blank=True)
    x_url = models.URLField(blank=True)

    class HeroStyle(models.TextChoices):
        MEDIA = "media", "Photo or video"
        CAROUSEL = "carousel", "Lookbook carousel"

    hero_style = models.CharField(max_length=10, choices=HeroStyle.choices, default=HeroStyle.MEDIA)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "site settings"
        verbose_name_plural = "site settings"

    def __str__(self):
        return "Site settings"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce a single row
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # the singleton cannot be deleted

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


LOOKBOOK_MIN = 3   # fewer than this and the homepage uses the normal hero
LOOKBOOK_MAX = 10


def clean_link(value):
    """Allow a site path (/shop/...) or a web address (https://...). Anything else, such as javascript:, is refused."""
    from django.core.exceptions import ValidationError

    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("/") and not value.startswith("//"):
        return value
    if value.lower().startswith(("https://", "http://")) and len(value) > 10:
        return value
    raise ValidationError("Use a page on this site such as /shop/ or a full web address starting with https://")


class LookbookSlide(TimeStampedModel):
    """One image in the homepage lookbook carousel, with the words and button that appear when it is at the front."""

    image = models.ImageField(upload_to="lookbook/", validators=[validate_image_extension, validate_image_size])
    alt_text = models.CharField(max_length=200, blank=True, help_text="Describe the picture for people who can't see it.")
    title = models.CharField("Headline", max_length=120)
    subtitle = models.CharField("Subheadline", max_length=200, blank=True)
    button_text = models.CharField(max_length=30, default="Shop now")
    product = models.ForeignKey("catalog.Product", null=True, blank=True, on_delete=models.SET_NULL, related_name="+",
                                help_text="Pick a product and the button opens its page. Or leave this empty and paste a link below.")
    link_url = models.CharField("Other link", max_length=300, blank=True)
    backdrop = models.CharField(
        "Background colour", max_length=7, default="#E9E1D2",
        validators=[RegexValidator(r"^#[0-9a-fA-F]{6}$", "Enter a colour such as #E9E1D2.")],
        help_text="The whole hero fades to this colour while this look is at the front. Text switches between dark and light automatically.")
    backdrop_word = models.CharField("Big background word", max_length=24, blank=True, help_text="Optional. A large, faint word behind the models, for example WINTER.")
    position = models.PositiveIntegerField(default=0, help_text="Lowest number comes first.")
    is_active = models.BooleanField("Show on the homepage", default=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.title

    @property
    def light_text(self):
        """Light text on a dark backdrop, chosen by contrast so the admin can never pick unreadable text."""
        from .colour import needs_light_text

        return needs_light_text(self.backdrop)

    def clean(self):
        from django.core.exceptions import ValidationError

        self.link_url = clean_link(self.link_url)
        self.backdrop = (self.backdrop or "#E9E1D2").upper()
        from .colour import HEX, is_readable

        # A malformed value is reported by the field's own validator; only judge real hex colours here.
        if HEX.match(self.backdrop) and not is_readable(self.backdrop):
            raise ValidationError({"backdrop": "That mid-tone makes the text hard to read. Choose a lighter or a darker colour."})
        if not self.product_id and not self.link_url:
            raise ValidationError("Choose a product or enter a link for the button.")

    @property
    def target_url(self):
        if self.product_id:
            return self.product.get_absolute_url()
        return self.link_url


class NewsletterSubscriber(TimeStampedModel):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        super().save(*args, **kwargs)
