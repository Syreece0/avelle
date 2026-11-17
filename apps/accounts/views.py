from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import AddressForm, LoginForm, ProfileForm, RegisterForm, StyledPasswordChangeForm
from .models import Address


def _safe_next(request, default="/"):
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return target
    return default


class AvelleLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        # Staff, managers and administrators land in the dashboard unless they were heading somewhere else.
        if self.request.user.is_authenticated and self.request.user.is_dashboard_user:
            return reverse("dashboard:overview")
        return super().get_default_redirect_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next"] = _safe_next(self.request, "")
        return context


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:overview")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(request, f"Welcome to AVELLE, {user.first_name}.")
        return redirect(_safe_next(request, "/"))
    return render(request, "accounts/register.html", {"form": form, "next": _safe_next(request, "")})


@require_POST
def logout_view(request):
    logout(request)
    messages.success(request, "You've been signed out.")
    return redirect("/")


@login_required
def overview(request):
    default_address = Address.objects.filter(user=request.user, is_default=True).first()
    return render(request, "accounts/overview.html", {"default_address": default_address, "section": "overview"})


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your details have been updated.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form, "section": "profile"})


@login_required
def password_change(request):
    form = StyledPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)  # keep this session signed in
        messages.success(request, "Your password has been changed.")
        return redirect("accounts:password_change")
    return render(request, "accounts/password_change.html", {"form": form, "section": "password"})


@login_required
def addresses(request):
    items = Address.objects.filter(user=request.user)
    return render(request, "accounts/addresses.html", {"addresses": items, "section": "addresses"})


@login_required
def address_edit(request, pk=None):
    instance = get_object_or_404(Address, pk=pk, user=request.user) if pk else None
    form = AddressForm(request.POST or None, instance=instance, user=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Address saved." if instance else "Address added.")
        return redirect(_safe_next(request, reverse("accounts:addresses")))
    return render(request, "accounts/address_form.html", {
        "form": form, "address": instance, "section": "addresses", "next": _safe_next(request, ""),
    })


@login_required
@require_POST
def address_delete(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    was_default = address.is_default
    address.delete()
    if was_default:
        replacement = Address.objects.filter(user=request.user).first()
        if replacement:
            replacement.is_default = True
            replacement.save(update_fields=["is_default"])
    messages.success(request, "Address removed.")
    return redirect("accounts:addresses")


@login_required
@require_POST
def address_default(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    Address.objects.filter(user=request.user, is_default=True).exclude(pk=address.pk).update(is_default=False)
    address.is_default = True
    address.save(update_fields=["is_default"])
    messages.success(request, "Default address updated.")
    return redirect("accounts:addresses")


@login_required
def notifications(request):
    """The customer's own in-app notifications (order updates, welcome). Opening the page marks them read."""
    from django.core.paginator import Paginator

    from apps.notifications.models import Notification

    queryset = Notification.objects.filter(recipient=request.user, audience=Notification.Audience.CUSTOMER).order_by("-created_at", "-pk")
    page = Paginator(queryset, 15).get_page(request.GET.get("page"))
    items = list(page.object_list)
    unread_ids = [n.pk for n in items if not n.is_read]
    # Only internal links are followed; anything else is shown as plain text.
    for n in items:
        n.safe_link = n.link_url if n.link_url.startswith("/") and not n.link_url.startswith("//") else ""
    response = render(request, "accounts/notifications.html", {"page": page, "items": items, "unread_ids": set(unread_ids), "section": "notifications"})
    if unread_ids:
        Notification.objects.filter(pk__in=unread_ids, recipient=request.user).update(is_read=True)
    return response
