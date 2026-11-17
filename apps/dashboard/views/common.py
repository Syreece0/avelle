from urllib.parse import urlencode

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.shortcuts import render

from .. import access


def page(request, template, active, **context):
    """Render a dashboard page with the sidebar, active section and permission flags filled in."""
    perms = access.user_permissions(request.user)
    items = access.nav_items(request.user)
    unread = next((i["count"] for i in items if i["key"] == "notifications"), 0)
    context.update(nav_items=items, active_nav=active, can={p: True for p in perms}, unread_notifications=unread)
    return render(request, template, context)


def paginate(request, queryset, per_page=20):
    if hasattr(queryset, "ordered") and not queryset.ordered:
        queryset = queryset.order_by("-pk")  # stable pages: unordered querysets can repeat or skip rows
    paginator = Paginator(queryset, per_page)
    try:
        number = paginator.page(request.GET.get("page") or 1)
    except PageNotAnInteger:
        number = paginator.page(1)
    except EmptyPage:
        number = paginator.page(paginator.num_pages)
    return number


def keep_query(request, drop=("page",)):
    """The current query string without ``page``, ready to append '&page=N' (or '?page=N' when empty)."""
    pairs = [(k, v) for k, v in request.GET.items() if k not in drop and v != ""]
    return urlencode(pairs)


def clean_choice(value, allowed, default=""):
    return value if value in allowed else default
