"""Small shared helpers."""
from django.utils.text import slugify


def unique_slugify(instance, value, queryset=None, slug_field_name="slug"):
    """Return a slug for ``value`` that is unique within ``queryset``.

    ``queryset`` defaults to every row of the instance's model; pass a
    narrower one (for example, siblings under one parent category) when the
    slug only has to be unique within a scope.
    """
    model = instance.__class__
    max_length = model._meta.get_field(slug_field_name).max_length
    base = slugify(value)[:max_length] or "item"

    if queryset is None:
        queryset = model._default_manager.all()
    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)

    slug = base
    counter = 2
    while queryset.filter(**{slug_field_name: slug}).exists():
        suffix = f"-{counter}"
        slug = f"{base[: max_length - len(suffix)]}{suffix}"
        counter += 1
    return slug


def client_ip(request):
    """Best-effort client address (Render sits behind a proxy that sets X-Forwarded-For)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")) or "unknown"


def cloudinary_optimised(url, width):
    """Ask Cloudinary for a right-sized, modern-format copy: f_auto (WebP/AVIF), q_auto, width capped.

    Only Cloudinary delivery URLs are touched; local /media/ paths and anything else pass through
    unchanged, so development without Cloudinary keeps working. Already-transformed URLs are left alone.
    """
    marker = "/image/upload/"
    if not url or marker not in url or "res.cloudinary.com" not in url:
        return url
    head, tail = url.split(marker, 1)
    if tail.startswith(("f_", "q_", "w_", "c_")):
        return url
    return f"{head}{marker}f_auto,q_auto,c_limit,w_{int(width)}/{tail}"
