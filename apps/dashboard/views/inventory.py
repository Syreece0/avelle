from django.contrib import messages
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect

from apps.catalog.models import Inventory, ProductVariant, StockAdjustment

from .. import services
from ..access import dashboard_required
from ..forms import StockAdjustForm, ThresholdForm
from ..services import DashboardError
from .common import clean_choice, keep_query, page, paginate


@dashboard_required("inventory")
def inventory(request):
    q = (request.GET.get("q") or "").strip()[:80]
    state = clean_choice(request.GET.get("state"), {"low", "out", "in"})
    qs = Inventory.objects.select_related("variant__product", "variant__size", "variant__colour").order_by("quantity", "variant__product__name")
    if q:
        qs = qs.filter(Q(variant__product__name__icontains=q) | Q(variant__sku__icontains=q))
    if state == "out":
        qs = qs.filter(quantity=0)
    elif state == "low":
        qs = qs.filter(quantity__gt=0, quantity__lte=F("low_stock_threshold"))
    elif state == "in":
        qs = qs.filter(quantity__gt=F("low_stock_threshold"))
    base = Inventory.objects.filter(variant__is_active=True)
    summary = {
        "out": base.filter(quantity=0).count(),
        "low": base.filter(quantity__gt=0, quantity__lte=F("low_stock_threshold")).count(),
        "all": Inventory.objects.count(),
    }
    return page(request, "dashboard/inventory.html", "inventory", page_obj=paginate(request, qs, 25), q=q, state=state,
                summary=summary, qs=keep_query(request))


@dashboard_required("inventory")
def variant_stock(request, pk):
    variant = get_object_or_404(ProductVariant.objects.select_related("product", "size", "colour"), pk=pk)
    inv, _ = Inventory.objects.get_or_create(variant=variant)
    adjust = StockAdjustForm(request.POST or None, prefix="adj") if request.POST.get("form") == "adjust" else StockAdjustForm(prefix="adj")
    threshold = ThresholdForm(request.POST, instance=inv, prefix="thr") if request.POST.get("form") == "threshold" else ThresholdForm(instance=inv, prefix="thr")
    if request.method == "POST":
        if request.POST.get("form") == "adjust" and adjust.is_valid():
            try:
                services.adjust_stock(variant.pk, user=request.user, **adjust.as_service_kwargs())
                messages.success(request, "Stock updated.")
                return redirect("dashboard:variant_stock", pk=pk)
            except DashboardError as error:
                adjust.add_error(None, str(error))
        elif request.POST.get("form") == "threshold" and threshold.is_valid():
            threshold.save()
            messages.success(request, "Alert level saved.")
            return redirect("dashboard:variant_stock", pk=pk)
    history = variant.stock_adjustments.select_related("created_by")
    return page(request, "dashboard/variant_stock.html", "inventory", variant=variant, inv=inv, adjust_form=adjust,
                threshold_form=threshold, page_obj=paginate(request, history, 15), qs=keep_query(request))


@dashboard_required("inventory")
def stock_history(request):
    reason = clean_choice(request.GET.get("reason"), {r for r, _ in StockAdjustment.Reason.choices})
    qs = StockAdjustment.objects.select_related("variant__product", "variant__size", "variant__colour", "created_by")
    if reason:
        qs = qs.filter(reason=reason)
    return page(request, "dashboard/stock_history.html", "inventory", page_obj=paginate(request, qs, 30), reason=reason,
                reasons=StockAdjustment.Reason.choices, qs=keep_query(request))
