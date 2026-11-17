from django.db import models

from apps.core.models import TimeStampedModel
from apps.core.storage import homepage_media_storage
from apps.core.validators import is_video_name, validate_media_extension, validate_media_size


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
