from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .models import NewsletterSubscriber, SiteContent

RATE_LIMIT = 8            # attempts per address per hour
RATE_WINDOW = 60 * 60


def _client_ip(request):
    # Render and most hosts sit behind a proxy that sets X-Forwarded-For.
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")) or "unknown"


def _rate_limited(request):
    key = f"newsletter:{_client_ip(request)}"
    cache.add(key, 0, RATE_WINDOW)
    try:
        return cache.incr(key) > RATE_LIMIT
    except ValueError:  # key expired between add and incr
        cache.set(key, 1, RATE_WINDOW)
        return False


@require_POST
def newsletter_subscribe(request):
    """Subscribe an email address. Returns JSON for fetch() calls, otherwise redirects back."""
    wants_json = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or "application/json" in request.headers.get("accept", "")
    )

    def respond(ok, message, status=200):
        if wants_json:
            return JsonResponse({"ok": ok, "message": message}, status=status)
        (messages.success if ok else messages.error)(request, message)
        target = request.POST.get("next", "")
        if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
            target = "/"
        return redirect(f"{target}#newsletter")

    # Honeypot: real visitors never see or fill this field. Pretend success to bots.
    if request.POST.get("company"):
        return respond(True, "Thank you for subscribing.")

    if _rate_limited(request):
        return respond(False, "Too many attempts. Please try again later.", status=429)

    email = (request.POST.get("email") or "").strip().lower()
    try:
        if not email or len(email) > 254:
            raise ValidationError("empty")
        validate_email(email)
    except ValidationError:
        return respond(False, "Please enter a valid email address.", status=400)

    subscriber, created = NewsletterSubscriber.objects.get_or_create(email=email)
    if created:
        return respond(True, "Thank you for subscribing. Welcome to AVELLE.")
    if subscriber.is_active:
        return respond(True, "You are already on the list. Thank you.")
    subscriber.is_active = True
    subscriber.unsubscribed_at = None
    subscriber.save(update_fields=["is_active", "unsubscribed_at", "updated_at"])
    return respond(True, "Welcome back. You are subscribed again.")


def info_page(request, key):
    """Public information pages (About, Privacy, Terms, Shipping, Returns), managed in the dashboard."""
    try:
        page = SiteContent.objects.get(key=key, kind=SiteContent.Kind.PAGE, is_published=True)
    except SiteContent.DoesNotExist:
        raise Http404("Page not found")
    return render(request, "content/page.html", {"page": page})
