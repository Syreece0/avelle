import csv
import secrets

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.content.models import LOOKBOOK_MAX, LOOKBOOK_MIN, LookbookSlide, NewsletterSubscriber, SiteContent, SiteSettings

from .. import rules
from ..access import dashboard_required
from ..forms import HOME_BLOCKS, AnnouncementForm, HeroStyleForm, HomepageBlockForm, LookbookSlideForm, PageForm, SiteSettingsForm
from .common import clean_choice, keep_query, page, paginate
from .reports import csv_response

Kind = SiteContent.Kind


def _tabs(active):
    return [("dashboard:content_homepage", "Homepage", "homepage"), ("dashboard:content_lookbook", "Lookbook", "lookbook"), ("dashboard:content_pages", "Pages", "pages"),
            ("dashboard:content_announcements", "Announcements", "announcements"), ("dashboard:content_settings", "Contact & social", "settings")], active


def _content_page(request, template, tab, **ctx):
    tabs, active = _tabs(tab)
    return page(request, template, "content", tabs=tabs, tab=active, **ctx)


@dashboard_required("content")
def homepage(request):
    existing = {c.key: c for c in SiteContent.objects.filter(kind=Kind.HOMEPAGE)}
    blocks = [{"key": k, "config": cfg, "obj": existing.get(k)} for k, cfg in HOME_BLOCKS.items()]
    return _content_page(request, "dashboard/content_homepage.html", "homepage", blocks=blocks)


@dashboard_required("content")
def homepage_edit(request, key):
    if key not in HOME_BLOCKS:
        return redirect("dashboard:content_homepage")
    obj = SiteContent.objects.filter(key=key, kind=Kind.HOMEPAGE).first() or SiteContent(key=key, kind=Kind.HOMEPAGE)
    form = HomepageBlockForm(request.POST or None, request.FILES or None, instance=obj, key=key)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"{HOME_BLOCKS[key]['label']} saved. Changes show on the homepage straight away.")
        return redirect("dashboard:content_homepage")
    return page(request, "dashboard/simple_form.html", "content", form=form, title=f"Edit: {HOME_BLOCKS[key]['label']}",
                back=("dashboard:content_homepage", "Website content"), multipart=True)


@dashboard_required("content")
def lookbook(request):
    settings_obj = SiteSettings.load()
    style_form = HeroStyleForm(request.POST or None, instance=settings_obj)
    if request.method == "POST" and style_form.is_valid():
        style_form.save()
        messages.success(request, "Homepage hero updated.")
        return redirect("dashboard:content_lookbook")
    slides = list(LookbookSlide.objects.select_related("product"))
    active = sum(1 for slide in slides if slide.is_active)
    return _content_page(request, "dashboard/content_lookbook.html", "lookbook", slides=slides, style_form=style_form,
                         active_count=active, minimum=LOOKBOOK_MIN, maximum=LOOKBOOK_MAX,
                         live=settings_obj.hero_style == SiteSettings.HeroStyle.CAROUSEL and active >= LOOKBOOK_MIN)


@dashboard_required("content")
def lookbook_edit(request, pk=None):
    obj = get_object_or_404(LookbookSlide, pk=pk) if pk else LookbookSlide()
    if not pk and LookbookSlide.objects.count() >= LOOKBOOK_MAX:
        messages.error(request, f"The lookbook holds at most {LOOKBOOK_MAX} slides. Remove one first.")
        return redirect("dashboard:content_lookbook")
    form = LookbookSlideForm(request.POST or None, request.FILES or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Slide saved.")
        return redirect("dashboard:content_lookbook")
    return page(request, "dashboard/simple_form.html", "content", form=form, title="Edit slide" if pk else "New slide",
                back=("dashboard:content_lookbook", "Lookbook"), multipart=True,
                delete_url=f"/dashboard/content/lookbook/{pk}/delete/" if pk else "", delete_message="Delete this slide?" if pk else "")


@dashboard_required("content")
@require_POST
def lookbook_delete(request, pk):
    get_object_or_404(LookbookSlide, pk=pk).delete()
    messages.success(request, "Slide deleted.")
    return redirect("dashboard:content_lookbook")


@dashboard_required("content")
def pages(request):
    return _content_page(request, "dashboard/content_pages.html", "pages", items=SiteContent.objects.filter(kind=Kind.PAGE))


@dashboard_required("content")
def page_edit(request, pk=None):
    obj = get_object_or_404(SiteContent, pk=pk, kind=Kind.PAGE) if pk else SiteContent(kind=Kind.PAGE)
    form = PageForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Page saved.")
        return redirect("dashboard:content_pages")
    return page(request, "dashboard/simple_form.html", "content", form=form, title="Edit page" if pk else "New page",
                back=("dashboard:content_pages", "Pages"),
                delete_url=f"/dashboard/content/pages/{pk}/delete/" if pk else "", delete_message=f"Delete the page “{obj.title}”?" if pk else "")


@dashboard_required("content")
@require_POST
def page_delete(request, pk):
    get_object_or_404(SiteContent, pk=pk, kind=Kind.PAGE).delete()
    messages.success(request, "Page deleted.")
    return redirect("dashboard:content_pages")


@dashboard_required("content")
def announcements(request):
    return _content_page(request, "dashboard/content_announcements.html", "announcements", items=SiteContent.objects.filter(kind=Kind.ANNOUNCEMENT))


@dashboard_required("content")
def announcement_edit(request, pk=None):
    obj = get_object_or_404(SiteContent, pk=pk, kind=Kind.ANNOUNCEMENT) if pk else SiteContent(kind=Kind.ANNOUNCEMENT, key="announcement-" + secrets.token_hex(4))
    form = AnnouncementForm(request.POST or None, instance=obj)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Announcement saved.")
        return redirect("dashboard:content_announcements")
    return page(request, "dashboard/simple_form.html", "content", form=form, title="Edit announcement" if pk else "New announcement",
                back=("dashboard:content_announcements", "Announcements"),
                delete_url=f"/dashboard/content/announcements/{pk}/delete/" if pk else "", delete_message="Delete this announcement?" if pk else "")


@dashboard_required("content")
@require_POST
def announcement_delete(request, pk):
    get_object_or_404(SiteContent, pk=pk, kind=Kind.ANNOUNCEMENT).delete()
    messages.success(request, "Announcement deleted.")
    return redirect("dashboard:content_announcements")


@dashboard_required("content")
def site_settings(request):
    form = SiteSettingsForm(request.POST or None, instance=SiteSettings.load())
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Contact details saved.")
        return redirect("dashboard:content_settings")
    return _content_page(request, "dashboard/content_settings.html", "settings", form=form)


# ---- newsletter (marketing)
@dashboard_required("promotions")
def newsletter(request):
    q = (request.GET.get("q") or "").strip()[:80]
    state = clean_choice(request.GET.get("state"), {"active", "unsubscribed"})
    qs = NewsletterSubscriber.objects.all()
    if q:
        qs = qs.filter(email__icontains=q)
    if state:
        qs = qs.filter(is_active=(state == "active"))
    if request.GET.get("export") == "csv":
        rows = [[s.email, "active" if s.is_active else "unsubscribed", s.created_at.strftime("%Y-%m-%d")] for s in qs.order_by("created_at")]
        return csv_response("avelle-newsletter.csv", ["Email", "Status", "Subscribed"], rows)
    totals = {"active": NewsletterSubscriber.objects.filter(is_active=True).count(), "all": NewsletterSubscriber.objects.count()}
    return page(request, "dashboard/newsletter.html", "newsletter", page_obj=paginate(request, qs, 30), q=q, state=state, totals=totals,
                qs=keep_query(request), export_qs=keep_query(request, drop=("page", "export")))


@dashboard_required("promotions")
@require_POST
def newsletter_toggle(request, pk):
    sub = get_object_or_404(NewsletterSubscriber, pk=pk)
    from django.utils import timezone

    sub.is_active = not sub.is_active
    sub.unsubscribed_at = None if sub.is_active else timezone.now()
    sub.save(update_fields=["is_active", "unsubscribed_at", "updated_at"])
    messages.success(request, f"{sub.email} is now {'subscribed' if sub.is_active else 'unsubscribed'}.")
    return redirect(request.POST.get("next") if (request.POST.get("next") or "").startswith("/dashboard/") else "dashboard:newsletter")
