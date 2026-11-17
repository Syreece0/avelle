from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from apps.content.models import SiteContent
from apps.core.validators import MAX_IMAGE_BYTES, MAX_VIDEO_BYTES
from apps.dashboard.forms import HomepageBlockForm


@override_settings(MEDIA_ROOT="/tmp/avelle-test-media")
class HomepageMediaUploads(TestCase):
    def form(self, key, upload):
        instance = SiteContent(key=key, kind=SiteContent.Kind.HOMEPAGE, title="x")
        data = {"title": "Dressed in|quiet confidence", "subtitle": "s", "body": "b", "is_published": "on"}
        return HomepageBlockForm(data, {"image": upload}, instance=instance, key=key)

    def test_hero_accepts_large_image(self):
        big = SimpleUploadedFile("hero.jpg", b"0" * (6 * 1024 * 1024), content_type="image/jpeg")
        self.assertTrue(self.form("hero", big).is_valid())  # 6 MB used to be rejected

    def test_hero_accepts_video(self):
        video = SimpleUploadedFile("loop.mp4", b"0" * 1024, content_type="video/mp4")
        form = self.form("hero", video)
        self.assertTrue(form.is_valid(), form.errors)

    def test_other_blocks_reject_video(self):
        video = SimpleUploadedFile("loop.mp4", b"0" * 1024, content_type="video/mp4")
        self.assertFalse(self.form("editorial", video).is_valid())

    def test_svg_and_executables_are_rejected(self):
        for name in ("logo.svg", "run.exe", "page.html"):
            upload = SimpleUploadedFile(name, b"x", content_type="application/octet-stream")
            self.assertFalse(self.form("hero", upload).is_valid(), name)

    def test_size_limits(self):
        self.assertEqual(MAX_IMAGE_BYTES, 20 * 1024 * 1024)
        self.assertEqual(MAX_VIDEO_BYTES, 100 * 1024 * 1024)

    def test_is_video_property(self):
        block = SiteContent(key="hero", kind=SiteContent.Kind.HOMEPAGE, title="x", image="content/loop.mp4")
        self.assertTrue(block.is_video)
        block.image = "content/photo.jpg"
        self.assertFalse(block.is_video)
