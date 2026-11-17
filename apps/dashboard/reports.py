"""Report queries. Each returns the same shape so the page and the CSV export share one source of truth:

    {"title", "note", "summary": [(label, value, is_money)], "columns": [...], "rows": [[...]], "uses_range": bool}

Sales figures use the same definition as the overview: orders that are paid and not refunded or cancelled,
counted on the day payment arrived. Product revenue is the line total before any order-level discount code.
"""
from datetime import datetime, time, timedelta
from decimal import Decimal

from django.db.models import Count, Max, Sum
from django.utils import timezone

from apps.catalog.models import Inventory
from apps.orders.models import Order, OrderItem

from . import rules

ZERO = Decimal("0.00")


def bounds(start_date, end_date):
    start = timezone.make_aware(datetime.combine(start_date, time.min))
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min))
    return start, end


def _sales(start, end):
    return Order.objects.filter(status__in=rules.REVENUE_STATUSES, paid_at__gte=start, paid_at__lt=end)


def _local(dt):
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M") if dt else ""


def sales(start, end):
    qs = _sales(start, end)
    t = qs.aggregate(revenue=Sum("total"), n=Count("id"), discount=Sum("discount_amount"), delivery=Sum("delivery_charge"))
    revenue, n = t["revenue"] or ZERO, t["n"] or 0
    rows = [
        [o.order_number, _local(o.paid_at), o.customer_name, o.email, o.state, o.units or 0, o.subtotal, o.discount_amount,
         o.delivery_charge, o.total, o.discount_code_text, o.get_status_display()]
        for o in qs.annotate(units=Sum("items__quantity")).order_by("paid_at")
    ]
    return {"title": "Sales", "note": "One row per paid order.", "uses_range": True,
            "summary": [("Revenue", revenue, True), ("Orders", n, False), ("Average order", (revenue / n).quantize(Decimal("0.01")) if n else ZERO, True),
                        ("Discounts given", t["discount"] or ZERO, True), ("Delivery charged", t["delivery"] or ZERO, True)],
            "columns": ["Order", "Paid", "Customer", "Email", "State", "Units", "Subtotal", "Discount", "Delivery", "Total", "Code", "Status"],
            "rows": rows}


def products(start, end):
    rows = [
        [r["product_name"], r["units"], r["orders"], r["revenue"]]
        for r in OrderItem.objects.filter(order__in=_sales(start, end)).values("product_name")
        .annotate(units=Sum("quantity"), orders=Count("order", distinct=True), revenue=Sum("line_total")).order_by("-revenue", "product_name")
    ]
    return {"title": "Products", "note": "Units and revenue by product, before order-level discount codes.", "uses_range": True,
            "summary": [("Products sold", len(rows), False), ("Units", sum(r[1] for r in rows), False), ("Revenue", sum((r[3] for r in rows), ZERO), True)],
            "columns": ["Product", "Units", "Orders", "Revenue"], "rows": rows}


def customers(start, end):
    rows = [
        [r["email"], r["name"], r["orders"], r["spent"], _local(r["last"])]
        for r in _sales(start, end).values("email").annotate(name=Max("customer_name"), orders=Count("id"), spent=Sum("total"), last=Max("paid_at")).order_by("-spent", "email")
    ]
    repeat = sum(1 for r in rows if r[2] > 1)
    return {"title": "Customers", "note": "Everyone who paid in the period, guests included, grouped by email.", "uses_range": True,
            "summary": [("Customers", len(rows), False), ("Repeat customers", repeat, False), ("Spent", sum((r[3] for r in rows), ZERO), True)],
            "columns": ["Email", "Name", "Orders", "Spent", "Last order"], "rows": rows}


def states(start, end):
    rows = [
        [r["state"], r["orders"], r["revenue"], r["delivery"]]
        for r in _sales(start, end).values("state").annotate(orders=Count("id"), revenue=Sum("total"), delivery=Sum("delivery_charge")).order_by("-revenue", "state")
    ]
    return {"title": "Delivery states", "note": "Where orders were delivered.", "uses_range": True,
            "summary": [("States", len(rows), False), ("Orders", sum(r[1] for r in rows), False), ("Revenue", sum((r[2] for r in rows), ZERO), True)],
            "columns": ["State", "Orders", "Revenue", "Delivery charged"], "rows": rows}


def stock(start=None, end=None):
    rows, units, value = [], 0, ZERO
    for inv in Inventory.objects.filter(variant__is_active=True).select_related("variant__product", "variant__size", "variant__colour").order_by("variant__product__name", "variant__size__sort_order"):
        v = inv.variant
        line = v.unit_price * inv.quantity
        units += inv.quantity
        value += line
        rows.append([v.product.name, v.size.name, v.colour.name, v.sku, inv.quantity, v.unit_price, line])
    return {"title": "Stock", "note": "Current stock on hand, valued at selling price. Not affected by the date range.", "uses_range": False,
            "summary": [("Variants", len(rows), False), ("Units in stock", units, False), ("Value at selling price", value, True)],
            "columns": ["Product", "Size", "Colour", "SKU", "In stock", "Unit price", "Stock value"], "rows": rows}


REPORTS = {"sales": sales, "products": products, "customers": customers, "states": states, "stock": stock}
TABS = [("sales", "Sales"), ("products", "Products"), ("customers", "Customers"), ("states", "States"), ("stock", "Stock")]
