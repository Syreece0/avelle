from django.contrib import messages
from django.forms import modelformset_factory
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.catalog.models import Review
from apps.core.constants import NIGERIAN_STATES
from apps.orders.models import DeliveryZone

from ..access import dashboard_required
from ..forms import DeliveryZoneForm
from .common import clean_choice, keep_query, page, paginate

ZoneFormSet = modelformset_factory(DeliveryZone, form=DeliveryZoneForm, extra=0)


@dashboard_required("delivery")
def delivery(request):
    queryset = DeliveryZone.objects.order_by("state")
    formset = ZoneFormSet(request.POST or None, queryset=queryset)
    if request.method == "POST" and formset.is_valid():
        formset.save()
        messages.success(request, "Delivery charges saved.")
        return redirect("dashboard:delivery")
    covered = set(queryset.values_list("state", flat=True))
    return page(request, "dashboard/delivery.html", "delivery", formset=formset, missing=[s for s in NIGERIAN_STATES if s not in covered],
                active_count=queryset.filter(is_active=True).count())


@dashboard_required("delivery")
@require_POST
def delivery_add_missing(request):
    covered = set(DeliveryZone.objects.values_list("state", flat=True))
    new = [DeliveryZone(state=s, is_active=False) for s in NIGERIAN_STATES if s not in covered]
    DeliveryZone.objects.bulk_create(new)
    messages.success(request, f"{len(new)} states added. They're switched off until you set a charge and turn them on.")
    return redirect("dashboard:delivery")


@dashboard_required("reviews")
def reviews(request):
    state = clean_choice(request.GET.get("state"), {"approved", "all"}, "pending")
    qs = Review.objects.select_related("product", "user")
    if state == "pending":
        qs = qs.filter(is_approved=False)
    elif state == "approved":
        qs = qs.filter(is_approved=True)
    return page(request, "dashboard/reviews.html", "reviews", page_obj=paginate(request, qs), state=state, qs=keep_query(request))


@dashboard_required("reviews")
@require_POST
def review_action(request, pk):
    review = get_object_or_404(Review, pk=pk)
    action = request.POST.get("action")
    if action in ("approve", "unapprove"):
        review.is_approved = action == "approve"
        review.save(update_fields=["is_approved", "updated_at"])
        messages.success(request, "Review " + ("published." if review.is_approved else "hidden."))
    elif action == "delete":
        review.delete()
        messages.success(request, "Review deleted.")
    nxt = request.POST.get("next", "")
    return redirect(nxt if nxt.startswith("/dashboard/") else "dashboard:reviews")
