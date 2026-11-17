"""Storage for homepage media that may be an image *or* a video.

In development files go to MEDIA_ROOT like everything else. In production (Cloudinary configured) the file is
uploaded with ``resource_type="auto"`` and the stored name records what Cloudinary made of it, for example
``image:content/abc123`` or ``video:content/abc123``, so the right delivery URL can be built later.
"""
from django.conf import settings
from django.core.files.storage import FileSystemStorage, Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class CloudinaryAnyMediaStorage(Storage):
    LARGE = 20 * 1024 * 1024  # larger files are sent in chunks

    @staticmethod
    def _configure():
        # Importing this module applies the CLOUDINARY_STORAGE settings to the cloudinary SDK.
        from cloudinary_storage import app_settings  # noqa: F401

    def _save(self, name, content):
        self._configure()
        import cloudinary.uploader

        content.seek(0)
        options = {"resource_type": "auto", "folder": "content", "use_filename": False, "unique_filename": True}
        if getattr(content, "size", 0) > self.LARGE:
            result = cloudinary.uploader.upload_large(content, chunk_size=6_000_000, **options)
        else:
            result = cloudinary.uploader.upload(content, **options)
        return f"{result['resource_type']}:{result['public_id']}"

    def exists(self, name):
        return False  # public ids are unique, so Django never needs to rename

    def get_available_name(self, name, max_length=None):
        return name

    def url(self, name):
        self._configure()
        from cloudinary.utils import cloudinary_url

        kind, _, public_id = str(name).partition(":")
        if not public_id:  # an older plain path
            return f"{settings.MEDIA_URL}{name}"
        options = {"resource_type": kind, "secure": True}
        if kind == "video":
            options["format"] = "mp4"
        return cloudinary_url(public_id, **options)[0]

    def delete(self, name):
        self._configure()
        import cloudinary.uploader

        kind, _, public_id = str(name).partition(":")
        if public_id:
            cloudinary.uploader.destroy(public_id, resource_type=kind)

    def size(self, name):
        return 0

    def open(self, name, mode="rb"):
        raise NotImplementedError("Media is served from Cloudinary, not opened through Django.")


def homepage_media_storage():
    """Callable used by SiteContent.image so the choice is made when Django starts, not frozen in a migration."""
    cloudinary = getattr(settings, "CLOUDINARY_STORAGE", None) or {}
    if cloudinary.get("CLOUD_NAME"):
        return CloudinaryAnyMediaStorage()
    return FileSystemStorage()
