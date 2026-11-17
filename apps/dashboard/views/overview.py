from django.db.models import Q

from apps.catalog.models import Product
from apps.orders.models import Order
from django.contrib.auth import get_user_model

from .. import stats
from ..access import can, dashboard_required
from ..rules import PERIODS
from .common import page


@dashboard_required("overview")
def overview(request):
    data = stats.overview(request.GET.get("period"))
    return page(request, "dashboard/overview.html", "overview", data=data, periods=list(PERIODS))


@dashboard_required("overview")
def search(request):
    q = (request.GET.get("q") or "").strip()[:80]
    orders = products = customers = []
    if q:
        if can(request.user, "orders"):
            orders = list(Order.objects.filter(
                Q(order_number__icontains=q) | Q(email__icontains=q) | Q(customer_name__icontains=q) | Q(phone__icontains=q)
            )[:8])
        if can(request.user, "catalogue"):
            products = list(Product.objects.filter(Q(name__icontains=q) | Q(variants__sku__icontains=q)).distinct()[:8])
        if can(request.user, "customers"):
            User = get_user_model()
            customers = list(User.objects.filter(
                Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
            )[:8])
    return page(request, "dashboard/search.html", "overview", q=q, orders=orders, products=products, customers=customers,
                total=len(orders) + len(products) + len(customers))
