"""Every number on the dashboard overview comes from here, computed from the database on each request.

Definitions (also shown to staff on the page):
- Revenue: ``total`` of orders that were paid and not refunded or cancelled, counted on the day payment arrived.
- Orders: the same set of orders.
- Average order: revenue / orders.
- Compared with the previous period of equal length.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from apps.catalog.models import Inventory, Review
from apps.orders.models import Order, OrderItem, OrderStatusHistory
from apps.payments.models import Payment

from . import rules

ZERO = Decimal("0.00")


def _window(days):
    today = timezone.localdate()
    start_date = today - timedelta(days=days - 1)
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    prev_start = timezone.make_aware(datetime.combine(start_date - timedelta(days=days), time.min))
    return start_date, start, prev_start


def _sales(start, end=None):
    qs = Order.objects.filter(status__in=rules.REVENUE_STATUSES, paid_at__gte=start)
    if end is not None:
        qs = qs.filter(paid_at__lt=end)
    return qs


def _summary(qs):
    row = qs.aggregate(revenue=Sum("total"), orders=Count("id"))
    revenue, orders = row["revenue"] or ZERO, row["orders"] or 0
    return {"revenue": revenue, "orders": orders, "average": (revenue / orders).quantize(Decimal("0.01")) if orders else ZERO}


def needs_attention():
    """Things a person should look at today, each with a count and where to go."""
    shortfall_orders = (
        OrderStatusHistory.objects.filter(note__startswith="STOCK SHORTFALL", order__status__in=[Order.Status.PAID, Order.Status.PROCESSING])
        .values("order_id").distinct().count()
    )
    refund_flags = Payment.objects.filter(gateway_response__icontains="refund required", status=Payment.Status.FAILED).count()
    return {
        "to_fulfil": Order.objects.filter(status=Order.Status.PAID).count(),
        "shortfalls": shortfall_orders,
        "refund_flags": refund_flags,
        "pending_reviews": Review.objects.filter(is_approved=False).count(),
        "low_stock": Inventory.objects.filter(variant__is_active=True, quantity__lte=F("low_stock_threshold")).count(),
    }


def overview(period):
    days = rules.period_days(period)
    start_date, start, prev_start = _window(days)
    User = get_user_model()

    now_sum, prev_sum = _summary(_sales(start)), _summary(_sales(prev_start, start))
    units = OrderItem.objects.filter(order__in=_sales(start)).aggregate(n=Sum("quantity"))["n"] or 0
    prev_units = OrderItem.objects.filter(order__in=_sales(prev_start, start)).aggregate(n=Sum("quantity"))["n"] or 0
    customers = User.objects.filter(role=User.Role.CUSTOMER, date_joined__gte=start).count()
    prev_customers = User.objects.filter(role=User.Role.CUSTOMER, date_joined__gte=prev_start, date_joined__lt=start).count()

    daily = (
        _sales(start).annotate(day=TruncDate("paid_at")).values("day").annotate(total=Sum("total")).values_list("day", "total")
    )
    bars = rules.scale_bars(rules.fill_daily_series(daily, start_date, days))

    status_rows = dict(Order.objects.filter(created_at__gte=start).values_list("status").annotate(n=Count("id")))
    status_breakdown = []
    top = max(status_rows.values(), default=0)
    for value, label in Order.Status.choices:
        n = status_rows.get(value, 0)
        status_breakdown.append({"value": value, "label": label, "count": n, "pct": int(n / top * 100) if top else 0})

    top_products = list(
        OrderItem.objects.filter(order__in=_sales(start))
        .values("product_name")
        .annotate(units=Sum("quantity"), revenue=Sum("line_total"))
        .order_by("-revenue")[:5]
    )
    best = max((p["revenue"] for p in top_products), default=ZERO)
    for p in top_products:
        p["pct"] = int(p["revenue"] / best * 100) if best else 0

    low_stock = list(
        Inventory.objects.filter(variant__is_active=True, quantity__lte=F("low_stock_threshold"))
        .select_related("variant__product", "variant__size", "variant__colour")
        .order_by("quantity", "variant__product__name")[:6]
    )
    recent = list(Order.objects.order_by("-created_at")[:8])

    return {
        "period": str(days),
        "days": days,
        "start_date": start_date,
        "end_date": timezone.localdate(),
        "cards": [
            {"label": "Revenue", "value": now_sum["revenue"], "money": True, "change": rules.percent_change(now_sum["revenue"], prev_sum["revenue"]), "icon": "card"},
            {"label": "Orders", "value": now_sum["orders"], "money": False, "change": rules.percent_change(now_sum["orders"], prev_sum["orders"]), "icon": "bag"},
            {"label": "Average order", "value": now_sum["average"], "money": True, "change": rules.percent_change(now_sum["average"], prev_sum["average"]), "icon": "chart"},
            {"label": "Units sold", "value": units, "money": False, "change": rules.percent_change(units, prev_units), "icon": "box"},
            {"label": "New customers", "value": customers, "money": False, "change": rules.percent_change(customers, prev_customers), "icon": "users"},
        ],
        "bars": bars,
        "bar_total": now_sum["revenue"],
        "has_sales": now_sum["orders"] > 0,
        "status_breakdown": status_breakdown,
        "top_products": top_products,
        "low_stock": low_stock,
        "recent_orders": recent,
        "attention": needs_attention(),
    }
