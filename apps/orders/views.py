from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import Address
from apps.cart import services as cart_services
from apps.payments.services import PaymentError, start_payment

from . import services
from .forms import CheckoutForm
from .models import Order


def _initial_for(user):
    if not user.is_authenticated:
        return {}
    address = Address.objects.filter(user=user, is_default=True).first() or Address.objects.filter(user=user).first()
    profile = getattr(user, "profile", None)
    initial = {"email": user.email, "customer_name": user.full_name if user.first_name else "", "phone": profile.phone if profile else ""}
    if address:
        initial.update({"customer_name": address.recipient_name, "phone": address.phone, "address_line1": address.line1,
                        "address_line2": address.line2, "city": address.city, "state": address.state, "landmark": address.landmark})
    return initial


def checkout(request):
    cart = cart_services.get_cart(request)
    summary = cart_services.summarise(cart, reconcile=True)
    if summary.is_empty:
        messages.info(request, "Your bag is empty.")
        return redirect("cart:cart")
    if summary.has_unavailable:
        messages.warning(request, "Please remove unavailable items before checking out.")
        return redirect("cart:cart")

    form = CheckoutForm(request.POST or None, initial=_initial_for(request.user), user=request.user)
    saved = list(Address.objects.filter(user=request.user)) if request.user.is_authenticated else []

    quote = services.build_quote(
        summary.subtotal, request.POST.get("state", form.initial.get("state", "")),
        request.POST.get("discount_code", ""), request.user, request.POST.get("email", form.initial.get("email", "")),
    )

    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        quote = services.build_quote(summary.subtotal, data["state"], data["discount_code"], request.user, data["email"])
        if data["discount_code"].strip() and quote.code is None:
            form.add_error("discount_code", quote.code_message or "That code isn't valid.")
        else:
            try:
                order = services.create_order(user=request.user, summary=summary, details=data, quote=quote)
            except services.CheckoutError as error:
                messages.error(request, str(error))
                return redirect("cart:cart")
            if data["save_address"] and request.user.is_authenticated and not Address.objects.filter(
                user=request.user, line1__iexact=data["address_line1"], city__iexact=data["city"]
            ).exists():
                Address.objects.create(
                    user=request.user, label="", recipient_name=data["customer_name"], phone=data["phone"],
                    line1=data["address_line1"], line2=data["address_line2"], city=data["city"], state=data["state"],
                    landmark=data["landmark"], is_default=not Address.objects.filter(user=request.user).exists(),
                )
            services.remember_order(request, order)
            try:
                return redirect(start_payment(order))
            except PaymentError as error:
                messages.error(request, str(error))
                return redirect("orders:detail", number=order.order_number)

    return render(request, "orders/checkout.html", {"form": form, "summary": summary, "quote": quote, "saved_addresses": saved})


@require_GET
def quote_json(request):
    """Live totals for the checkout summary. The server recomputes everything again on submit."""
    summary = cart_services.summarise(cart_services.get_cart(request))
    quote = services.build_quote(summary.subtotal, request.GET.get("state", ""), request.GET.get("code", ""), request.user, request.GET.get("email", ""))
    def fmt(value):
        return None if value is None else f"₦{value:,.0f}" if value == value.to_integral_value() else f"₦{value:,.2f}"
    return JsonResponse({
        "subtotal": fmt(quote.subtotal), "discount": fmt(quote.discount) if quote.discount else None,
        "delivery": "Free" if quote.free_delivery else fmt(quote.delivery), "total": fmt(quote.total),
        "eta": quote.eta, "code_ok": bool(quote.code), "code_message": quote.code_message,
        "state_ok": quote.zone is not None,
    })


@login_required
def order_list(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    return render(request, "orders/order_list.html", {"orders": orders, "section": "orders"})


def order_detail(request, number):
    order = get_object_or_404(Order.objects.prefetch_related("items", "status_history"), order_number=number)
    if not services.user_can_view(request, order):
        raise Http404()
    if order.is_paid:
        cart = cart_services.get_cart(request)
        if cart is not None and request.GET.get("paid") == "1":
            cart.items.all().delete()  # emptied once the customer has come back from a successful payment
    return render(request, "orders/order_detail.html", {"order": order, "section": "orders"})


@require_POST
def pay_again(request, number):
    order = get_object_or_404(Order, order_number=number)
    if not services.user_can_view(request, order):
        raise Http404()
    try:
        return redirect(start_payment(order))
    except PaymentError as error:
        messages.error(request, str(error))
        return redirect("orders:detail", number=order.order_number)
