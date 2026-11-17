from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.notifications import services

from ..access import dashboard_required
from .common import clean_choice, keep_query, page, paginate


@dashboard_required("overview")
def notifications(request):
    state = clean_choice(request.GET.get("state"), {"unread"}, "all")
    qs = services.visible_admin()
    if state == "unread":
        qs = qs.filter(is_read=False)
    return page(request, "dashboard/notifications.html", "notifications", page_obj=paginate(request, qs, 25), state=state, qs=keep_query(request))


@dashboard_required("overview")
@require_POST
def notification_read(request, pk):
    item = get_object_or_404(services.visible_admin(), pk=pk)
    item.is_read = True
    item.save(update_fields=["is_read", "updated_at"])
    target = item.link_url if request.POST.get("open") and item.link_url.startswith("/dashboard/") else "dashboard:notifications"
    return redirect(target)


@dashboard_required("overview")
@require_POST
def notifications_read_all(request):
    count = services.visible_admin().filter(is_read=False).update(is_read=True)
    messages.success(request, f"{count} notification{'s' if count != 1 else ''} marked as read.")
    return redirect("dashboard:notifications")
