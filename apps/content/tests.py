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


# ---------------------------------------------------------------- lookbook carousel hero
import io

from django.core.exceptions import ValidationError
from django.urls import reverse
from PIL import Image

from apps.accounts.models import CustomUser
from apps.content.models import LookbookSlide, SiteSettings


def png_upload(name="look.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (60, 80), (200, 180, 150)).save(buffer, "PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def make_slide(i, **kw):
    data = dict(title=f"Look {i}", subtitle="Sub", button_text="Shop now", link_url=f"/shop/?look={i}", position=i, image=f"lookbook/{i}.png")
    data.update(kw)
    return LookbookSlide.objects.create(**data)


@override_settings(MEDIA_ROOT="/tmp/avelle-test-media")
class LookbookModelAndHome(TestCase):
    def test_needs_a_product_or_a_link(self):
        slide = LookbookSlide(title="x", link_url="", image="a.png")
        with self.assertRaises(ValidationError):
            slide.clean()

    def test_unsafe_links_are_refused(self):
        for bad in ("javascript:alert(1)", "//evil.example/x", "ftp://x.example", "data:text/html,hi"):
            with self.assertRaises(ValidationError, msg=bad):
                LookbookSlide(title="x", link_url=bad, image="a.png").clean()
        for good in ("/shop/", "https://example.com/sale"):
            LookbookSlide(title="x", link_url=good, image="a.png").clean()

    def test_homepage_uses_carousel_only_with_enough_active_slides(self):
        from apps.core.homepage import build_lookbook

        for i in range(3):
            make_slide(i)
        self.assertEqual(build_lookbook(), [])                       # style not chosen yet
        settings_obj = SiteSettings.load()
        settings_obj.hero_style = SiteSettings.HeroStyle.CAROUSEL
        settings_obj.save()
        self.assertEqual(len(build_lookbook()), 3)
        LookbookSlide.objects.filter(title="Look 0").update(is_active=False)
        self.assertEqual(build_lookbook(), [])                       # only 2 active: fall back to the normal hero

    def test_homepage_renders_each_slides_own_link(self):
        for i in range(4):
            make_slide(i)
        settings_obj = SiteSettings.load()
        settings_obj.hero_style = SiteSettings.HeroStyle.CAROUSEL
        settings_obj.save()
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-lookbook")
        for i in range(4):
            self.assertContains(response, f'href="/shop/?look={i}"')

    def test_normal_hero_when_style_is_media(self):
        for i in range(4):
            make_slide(i)
        response = self.client.get("/")
        self.assertNotContains(response, "data-lookbook")


@override_settings(MEDIA_ROOT="/tmp/avelle-test-media")
class LookbookDashboard(TestCase):
    def setUp(self):
        self.admin = CustomUser.objects.create_user(email="lb-admin@example.com", password="pw-12345-pw", first_name="A", last_name="B", role="manager")
        self.client.force_login(self.admin)

    def test_page_renders_and_style_can_be_switched(self):
        self.assertEqual(self.client.get(reverse("dashboard:content_lookbook")).status_code, 200)
        response = self.client.post(reverse("dashboard:content_lookbook"), {"hero_style": "carousel"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(SiteSettings.load().hero_style, "carousel")

    def test_create_slide_with_image_and_link(self):
        response = self.client.post(reverse("dashboard:content_lookbook_new"), {
            "image": png_upload(), "alt_text": "A look", "title": "Quiet confidence", "subtitle": "Linen", "button_text": "Shop the edit",
            "product": "", "link_url": "/shop/?category=men", "position": "1", "is_active": "on"})
        self.assertEqual(response.status_code, 302, getattr(response, "context", None) and response.context["form"].errors)
        slide = LookbookSlide.objects.get()
        self.assertEqual(slide.target_url, "/shop/?category=men")

    def test_slide_without_destination_is_rejected(self):
        response = self.client.post(reverse("dashboard:content_lookbook_new"), {
            "image": png_upload(), "title": "No link", "button_text": "Shop", "product": "", "link_url": "", "position": "0", "is_active": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(LookbookSlide.objects.count(), 0)

    def test_limit_of_ten_slides(self):
        for i in range(10):
            make_slide(i)
        response = self.client.get(reverse("dashboard:content_lookbook_new"))
        self.assertEqual(response.status_code, 302)
