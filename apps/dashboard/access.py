"""Who may open which dashboard page, and the sidebar that reflects it."""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.db.models import F
from django.urls import reverse

from . import rules


def user_permissions(user):
    if not user.is_authenticated or not user.is_dashboard_user:
        return frozenset()
    return rules.permissions_for(user.role, user.is_superuser)


def can(user, permission):
    return permission in user_permissions(user)


def dashboard_required(permission="overview"):
    """Decorator: signed in, an active staff/manager/admin, and holding ``permission``.

    Anonymous visitors go to the sign-in page. Signed-in people without access get a plain 403 (not a
    redirect loop), and customers are not told the dashboard exists beyond that.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not request.user.is_dashboard_user or permission not in user_permissions(request.user):
                raise PermissionDenied
            request.dash_perms = user_permissions(request.user)
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


# key, label, icon, url name, permission, group heading
NAV = [
    ("overview", "Overview", "home", "dashboard:overview", "overview", None),
    ("notifications", "Notifications", "bell", "dashboard:notifications", "overview", None),
    ("orders", "Orders", "bag", "dashboard:orders", "orders", "Sales"),
    ("payments", "Payments", "card", "dashboard:payments", "payments", None),
    ("customers", "Customers", "users", "dashboard:customers", "customers", None),
    ("reports", "Reports", "chart", "dashboard:reports", "reports", None),
    ("products", "Products", "shirt", "dashboard:products", "catalogue", "Catalogue"),
    ("categories", "Categories", "layers", "dashboard:categories", "catalogue", None),
    ("attributes", "Attributes", "tag", "dashboard:attributes", "catalogue", None),
    ("inventory", "Inventory", "box", "dashboard:inventory", "inventory", None),
    ("reviews", "Reviews", "star", "dashboard:reviews", "reviews", None),
    ("discounts", "Discount codes", "percent", "dashboard:discounts", "promotions", "Marketing"),
    ("promotions", "Promotions", "image", "dashboard:promotions", "promotions", None),
    ("newsletter", "Newsletter", "mail", "dashboard:newsletter", "promotions", None),
    ("content", "Website content", "file", "dashboard:content_homepage", "content", "Content"),
    ("delivery", "Delivery charges", "truck", "dashboard:delivery", "delivery", "Settings"),
]


def nav_items(user):
    """Sidebar entries the user may open, each with a live count where something needs attention."""
    from apps.catalog.models import Inventory, Review
    from apps.orders.models import Order

    perms = user_permissions(user)
    counts = {}
    if "orders" in perms:
        counts["orders"] = Order.objects.filter(status=Order.Status.PAID).count()
    if "inventory" in perms:
        counts["inventory"] = Inventory.objects.filter(
            variant__is_active=True, quantity__lte=F("low_stock_threshold")
        ).count()
    if "overview" in perms:
        from apps.notifications.services import admin_unread_count

        counts["notifications"] = admin_unread_count()
    if "reviews" in perms:
        counts["reviews"] = Review.objects.filter(is_approved=False).count()

    items, last_group = [], None
    for key, label, icon, url_name, perm, group in NAV:
        if perm not in perms:
            continue
        item = {"key": key, "label": label, "icon": icon, "url": reverse(url_name), "count": counts.get(key, 0)}
        if group and group != last_group:
            item["group"] = group
        if group:
            last_group = group
        items.append(item)
    return items
