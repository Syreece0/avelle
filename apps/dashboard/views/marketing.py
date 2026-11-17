from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.promotions.models import DiscountCode, Promotion

from .. import rules
from ..access import dashboard_required
from ..forms import DiscountCodeForm, PromotionForm
from .common import clean_choice, keep_query, page, paginate


def _state(code, now):
    return rules.code_state(is_active=code.is_active, starts_at=code.starts_at, expires_at=code.expires_at,
                            times_used=code.times_used, usage_limit=code.usage_limit, now=now)


@dashboard_required("promotions")
def discounts(request):
    q = (request.GET.get("q") or "").strip()[:60]
    qs = DiscountCode.objects.all()
    if q:
        qs = qs.filter(code__icontains=q)
    page_obj = paginate(request, qs)
    now = timezone.now()
    for code in page_obj:
        code.state = _state(code, now)
    return page(request, "dashboard/discounts.html", "discounts", page_obj=page_obj, q=q, qs=keep_query(request))


@dashboard_required("promotions")
def discount_edit(request, pk=None):
    code = get_object_or_404(DiscountCode, pk=pk) if pk else None
    form = DiscountCodeForm(request.POST or None, instance=code)
    if request.method == "POST" and form.is_valid():
        saved = form.save()
        messages.success(request, f"Code {saved.code} saved.")
        return redirect("dashboard:discounts")
    redemptions = code.redemptions.select_related("order")[:15] if code else []
    return page(request, "dashboard/discount_form.html", "discounts", form=form, code=code, redemptions=redemptions,
                state=_state(code, timezone.now()) if code else "")


@dashboard_required("promotions")
@require_POST
def discount_delete(request, pk):
    code = get_object_or_404(DiscountCode, pk=pk)
    if code.times_used or code.redemptions.exists():
        code.is_active = False
        code.save(update_fields=["is_active", "updated_at"])
        messages.warning(request, f"{code.code} has been used on orders, so it was switched off instead of deleted.")
    else:
        code.delete()
        messages.success(request, f"{code.code} deleted.")
    return redirect("dashboard:discounts")


@dashboard_required("promotions")
def promotions(request):
    return page(request, "dashboard/promotions.html", "promotions", promos=Promotion.objects.all())


@dashboard_required("promotions")
def promotion_edit(request, pk=None):
    promo = get_object_or_404(Promotion, pk=pk) if pk else None
    form = PromotionForm(request.POST or None, request.FILES or None, instance=promo)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Promotion saved.")
        return redirect("dashboard:promotions")
    return page(request, "dashboard/simple_form.html", "promotions", form=form, title="Edit promotion" if promo else "New promotion",
                back=("dashboard:promotions", "Promotions"), multipart=True,
                delete_url=f"/dashboard/promotions/{pk}/delete/" if pk else "", delete_message="Delete this promotion banner?" if pk else "")


@dashboard_required("promotions")
@require_POST
def promotion_delete(request, pk):
    get_object_or_404(Promotion, pk=pk).delete()
    messages.success(request, "Promotion deleted.")
    return redirect("dashboard:promotions")
