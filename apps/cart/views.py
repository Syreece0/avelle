from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST

from . import services
from .services import CartError


def _is_ajax(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in request.headers.get("accept", "")


def _body_context(request, summary):
    return {"summary": summary}


@require_GET
def cart_page(request):
    cart = services.get_cart(request)
    summary = services.summarise(cart, reconcile=True)
    for note in summary.notes:
        messages.warning(request, note)
    return render(request, "cart/cart.html", {"summary": summary})


def _respond(request, *, ok, message="", note="", status=200, redirect_to="cart:cart"):
    """Same action, two answers: JSON for the page's JavaScript, a redirect for plain forms."""
    cart = services.get_cart(request)
    summary = services.summarise(cart)
    if _is_ajax(request):
        payload = {
            "ok": ok, "message": message, "note": note, "count": summary.count,
            "html": render_to_string("cart/_body.html", {"summary": summary}, request=request),
        }
        return JsonResponse(payload, status=status)
    if message:
        (messages.success if ok else messages.error)(request, message)
    if note:
        messages.info(request, note)
    return redirect(redirect_to)


@require_POST
def add(request):
    try:
        variant = services.resolve_variant(request.POST)
        quantity = request.POST.get("quantity", 1)
        cart = services.get_cart(request, create=True)
        item, note = services.add_item(cart, variant, quantity)
    except CartError as error:
        back = request.META.get("HTTP_REFERER") or "cart:cart"
        return _respond(request, ok=False, message=str(error), status=400, redirect_to=back)
    name = variant.product.name
    return _respond(request, ok=True, message=f"{name} added to your bag.", note=note)


@require_POST
def update(request):
    cart = services.get_cart(request)
    if cart is None:
        return _respond(request, ok=False, message="Your bag is empty.", status=400)
    try:
        services.set_quantity(cart, request.POST.get("item"), request.POST.get("quantity"))
    except CartError as error:
        return _respond(request, ok=False, message=str(error), status=400)
    return _respond(request, ok=True)


@require_POST
def remove(request):
    cart = services.get_cart(request)
    if cart is not None:
        services.remove_item(cart, request.POST.get("item"))
    return _respond(request, ok=True, message="Item removed from your bag.")
