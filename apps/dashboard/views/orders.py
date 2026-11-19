from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.orders.models import Order
from apps.payments.models import Payment
from apps.payments.services import reconcile_order

from .. import rules, services
from ..access import can, dashboard_required
from ..forms import OrderStatusForm, RefundForm, TrackingForm
from ..services import DashboardError
from .common import clean_choice, keep_query, page, paginate


@dashboard_required("orders")
def orders(request):
    status = clean_choice(request.GET.get("status"), {s for s, _ in Order.Status.choices})
    q = (request.GET.get("q") or "").strip()[:80]
    base = Order.objects.all()
    if q:
        base = base.filter(Q(order_number__icontains=q) | Q(email__icontains=q) | Q(customer_name__icontains=q) | Q(phone__icontains=q))
    counts = dict(base.values_list("status").annotate(n=Count("id")))
    tabs = [{"value": "", "label": "All", "count": sum(counts.values())}] + [
        {"value": v, "label": l, "count": counts.get(v, 0)} for v, l in Order.Status.choices
    ]
    qs = base.filter(status=status) if status else base
    qs = qs.annotate(item_count=Count("items", distinct=True))
    return page(request, "dashboard/orders.html", "orders", page_obj=paginate(request, qs), tabs=tabs, status=status, q=q,
                qs=keep_query(request))


def _detail(request, order, *, status_form=None, tracking_form=None, refund_form=None):
    payments = list(order.payments.prefetch_related("refunds").order_by("-created_at"))
    paid_payment = next((p for p in payments if p.status == Payment.Status.SUCCESS), None)
    refundable = rules.refundable_amount(paid_payment.amount, services.refunded_so_far(paid_payment)) if paid_payment else 0
    history = list(order.status_history.select_related("changed_by"))
    if status_form is None and rules.next_statuses(order.status):
        status_form = OrderStatusForm(order=order)
    if tracking_form is None and order.status in ("shipped", "delivered"):
        tracking_form = TrackingForm(initial={"courier": order.courier, "tracking_number": order.tracking_number})
    show_refund = can(request.user, "refunds") and paid_payment and refundable > 0 and order.status in rules.REFUNDABLE_ORDER_STATUSES
    if show_refund and refund_form is None:
        refund_form = RefundForm(refundable=refundable)
    return page(
        request, "dashboard/order_detail.html", "orders",
        order=order, items=order.items.all(), payments=payments, history=history,
        shortfalls=[h for h in history if h.note.startswith("STOCK SHORTFALL")],
        refund_flags=[p for p in payments if "refund required" in (p.gateway_response or "").lower()],
        status_form=status_form, tracking_form=tracking_form, refund_form=refund_form if show_refund else None,
        refundable=refundable, paid_payment=paid_payment,
    )


@dashboard_required("orders")
def order_detail(request, number):
    order = get_object_or_404(Order.objects.select_related("user", "delivery_zone"), order_number=number)
    return _detail(request, order)


@dashboard_required("orders")
@require_POST
def order_status(request, number):
    order = get_object_or_404(Order, order_number=number)
    form = OrderStatusForm(request.POST, order=order) if rules.next_statuses(order.status) else None
    if form is None:
        messages.error(request, "This order can't be moved any further.")
    elif form.is_valid():
        d = form.cleaned_data
        try:
            services.change_order_status(order.pk, d["status"], user=request.user, note=d["note"],
                                         courier=d["courier"], tracking_number=d["tracking_number"])
        except DashboardError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Order {order.order_number} updated.")
    else:
        return _detail(request, order, status_form=form)
    return redirect("dashboard:order_detail", number=number)


@dashboard_required("orders")
@require_POST
def order_check_payment(request, number):
    order = get_object_or_404(Order, order_number=number)
    if order.is_paid:
        messages.info(request, "This order is already marked as paid.")
    elif reconcile_order(order):
        messages.success(request, "Paystack confirms the payment. The order is now marked as paid.")
    else:
        messages.warning(request, "Paystack has no successful payment for this order yet. If the customer paid by transfer, try again in a few minutes.")
    return redirect("dashboard:order_detail", number=number)


@dashboard_required("orders")
@require_POST
def order_tracking(request, number):
    order = get_object_or_404(Order, order_number=number)
    form = TrackingForm(request.POST)
    if form.is_valid():
        try:
            services.update_tracking(order.pk, user=request.user, **form.cleaned_data)
            messages.success(request, "Tracking saved.")
        except DashboardError as error:
            messages.error(request, str(error))
    else:
        return _detail(request, order, tracking_form=form)
    return redirect("dashboard:order_detail", number=number)


@dashboard_required("refunds")
@require_POST
def order_refund(request, number):
    order = get_object_or_404(Order, order_number=number)
    payment = order.payments.filter(status=Payment.Status.SUCCESS).first()
    if payment is None:
        messages.error(request, "This order has no successful payment to refund.")
        return redirect("dashboard:order_detail", number=number)
    refundable = rules.refundable_amount(payment.amount, services.refunded_so_far(payment))
    form = RefundForm(request.POST, refundable=refundable)
    if form.is_valid():
        d = form.cleaned_data
        try:
            refund = services.refund_order(order.pk, amount=d["amount"], reason=d["reason"], user=request.user, restock=d["restock"])
        except DashboardError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"Refund of ₦{refund.amount:,.2f} submitted to Paystack ({refund.get_status_display().lower()}).")
    else:
        return _detail(request, order, refund_form=form)
    return redirect("dashboard:order_detail", number=number)
