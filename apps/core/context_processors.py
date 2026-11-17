"""Template context available on every storefront page.

Navigation, footer pages and contact details come from the database, so
administrators can change them from the dashboard without touching code.
"""
from django.conf import settings
from django.db.models import Prefetch

from apps.catalog.models import Category
from apps.content.models import SiteContent, SiteSettings


def storefront(request):
    # Dashboard pages have their own chrome and do not need storefront data.
    if request.path.startswith("/dashboard/"):
        return {}

    active_children = Category.objects.filter(is_active=True)
    nav_categories = list(
        Category.objects.filter(parent__isnull=True, is_active=True).prefetch_related(
            Prefetch("children", queryset=active_children, to_attr="active_children")
        )
    )
    info_pages = list(
        SiteContent.objects.filter(kind=SiteContent.Kind.PAGE, is_published=True).only("key", "title")
    )
    announcement = (
        SiteContent.objects.filter(kind=SiteContent.Kind.ANNOUNCEMENT, is_published=True)
        .order_by("position")
        .first()
    )
    return {
        "nav_categories": nav_categories,
        "info_pages": info_pages,
        "announcement": announcement,
        "site": SiteSettings.load(),
        "gsap_local": settings.GSAP_SELF_HOSTED,
    }
