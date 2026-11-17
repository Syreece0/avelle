"""Reusable validators, mainly for safe image uploads."""
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator

MAX_IMAGE_BYTES = 20 * 1024 * 1024   # 20 MB
MAX_VIDEO_BYTES = 100 * 1024 * 1024  # 100 MB
# Cloudinary's free plan caps images at 10 MB and video at 100 MB; raise your plan if you need more.

# SVG is deliberately absent: an SVG can carry script, so it is not a safe upload.
IMAGE_EXTENSIONS = ["jpg", "jpeg", "png", "webp", "gif", "bmp", "tif", "tiff"]
VIDEO_EXTENSIONS = ["mp4", "webm", "mov", "m4v"]

validate_image_extension = FileExtensionValidator(allowed_extensions=IMAGE_EXTENSIONS)
validate_media_extension = FileExtensionValidator(allowed_extensions=IMAGE_EXTENSIONS + VIDEO_EXTENSIONS)


def is_video_name(name):
    return str(name or "").lower().rsplit(".", 1)[-1] in VIDEO_EXTENSIONS or str(name or "").startswith("video:")


def validate_image_size(file):
    if file.size > MAX_IMAGE_BYTES:
        raise ValidationError(f"Images must be {MAX_IMAGE_BYTES // (1024 * 1024)} MB or smaller.")


def validate_media_size(file):
    """Images up to 20 MB, videos up to 100 MB."""
    if is_video_name(getattr(file, "name", "")):
        if file.size > MAX_VIDEO_BYTES:
            raise ValidationError(f"Videos must be {MAX_VIDEO_BYTES // (1024 * 1024)} MB or smaller.")
    else:
        validate_image_size(file)


def validate_phone(value):
    """Accepts +234 801 234 5678, 0801-234-5678, (0801) 2345678 ... 7 to 15 digits."""
    import re

    digits = re.sub(r"\D", "", value or "")
    if not re.fullmatch(r"[\d+\-\s()]+", value or "") or not 7 <= len(digits) <= 15:
        raise ValidationError("Enter a valid phone number, for example 0801 234 5678.")
