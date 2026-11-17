from django.contrib import messages
from django.contrib.auth import get_user_model
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect

from apps.orders.models import Order

from .. import rules, services
from ..access import can, dashboard_required
from ..forms import UserAccessForm
from .common import clean_choice, keep_query, page, paginate

User = get_user_model()


@dashboard_required("customers")
def customers(request):
    q = (request.GET.get("q") or "").strip()[:80]
    group = clean_choice(request.GET.get("group"), {"team"}, "customers")
    qs = User.objects.annotate(
        order_count=Count("orders", filter=Q(orders__status__in=rules.REVENUE_STATUSES), distinct=True),
        spent=Sum("orders__total", filter=Q(orders__status__in=rules.REVENUE_STATUSES)),
    )
    qs = qs.exclude(role=User.Role.CUSTOMER) if group == "team" else qs.filter(role=User.Role.CUSTOMER)
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
    return page(request, "dashboard/customers.html", "customers", page_obj=paginate(request, qs.order_by("-date_joined")), q=q,
                group=group, qs=keep_query(request))


@dashboard_required("customers")
def customer_detail(request, pk):
    person = get_object_or_404(User, pk=pk)
    form = None
    if can(request.user, "team"):
        form = UserAccessForm(request.POST or None, instance=person)
        if request.method == "POST":
            if form.is_valid():
                new_role, new_active = form.cleaned_data["role"], form.cleaned_data["is_active"]
                error = rules.can_change_access(
                    actor_id=request.user.pk, target_id=person.pk, target_role=person.role,
                    new_role=new_role, new_active=new_active, active_admins=services.admin_count(),
                )
                if error:
                    form.add_error(None, error)
                else:
                    form.save()
                    messages.success(request, "Access updated.")
                    return redirect("dashboard:customer_detail", pk=pk)
    orders = person.orders.order_by("-created_at")
    totals = orders.filter(status__in=rules.REVENUE_STATUSES).aggregate(spent=Sum("total"), n=Count("id"))
    return page(request, "dashboard/customer_detail.html", "customers", person=person, orders=orders[:15], totals=totals,
                addresses=person.addresses.all(), access_form=form,
                phone=getattr(getattr(person, "profile", None), "phone", ""))
