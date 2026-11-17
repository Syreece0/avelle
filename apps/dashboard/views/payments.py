from django.db.models import Q

from apps.payments.models import Payment, Refund

from ..access import dashboard_required
from .common import clean_choice, keep_query, page, paginate


@dashboard_required("payments")
def payments(request):
    view = clean_choice(request.GET.get("view"), {"refunds"}, "payments")
    q = (request.GET.get("q") or "").strip()[:80]
    status = ""
    if view == "refunds":
        qs = Refund.objects.select_related("payment__order", "processed_by")
        if q:
            qs = qs.filter(Q(payment__reference__icontains=q) | Q(payment__order__order_number__icontains=q))
    else:
        status = clean_choice(request.GET.get("status"), {s for s, _ in Payment.Status.choices})
        qs = Payment.objects.select_related("order")
        if q:
            qs = qs.filter(Q(reference__icontains=q) | Q(order__order_number__icontains=q) | Q(order__email__icontains=q))
        if status:
            qs = qs.filter(status=status)
    return page(request, "dashboard/payments.html", "payments", page_obj=paginate(request, qs), view=view, q=q, status=status,
                statuses=Payment.Status.choices, qs=keep_query(request))
