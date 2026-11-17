import json
import logging

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST


from .models import Payment
from .paystack import PaystackError, verify_signature
from .services import verify_reference

log = logging.getLogger(__name__)


@require_GET
def callback(request):
    """Paystack sends the customer back here. We never trust the query string: we ask Paystack."""
    reference = request.GET.get("reference") or request.GET.get("trxref") or ""
    try:
        payment = verify_reference(reference) if reference else None
    except PaystackError:
        log.exception("Verification failed for %s", reference)
        messages.warning(request, "We're confirming your payment. If you were charged, your order will update shortly.")
        payment = Payment.objects.filter(reference=reference).select_related("order").first()
    if payment is None:
        messages.error(request, "We couldn't find that payment.")
        return redirect("cart:cart")
    order = payment.order
    if payment.status == Payment.Status.SUCCESS:
        messages.success(request, "Payment received. Thank you.")
        return redirect(f"/orders/{order.order_number}/?paid=1")
    if payment.status in (Payment.Status.FAILED, Payment.Status.ABANDONED):
        messages.error(request, "The payment wasn't completed. You can try again below.")
    return redirect("orders:detail", number=order.order_number)


@csrf_exempt
@require_POST
def webhook(request):
    """Paystack server-to-server notification. Signed with HMAC-SHA512; unsigned requests are refused."""
    if not verify_signature(request.body, request.headers.get("x-paystack-signature", ""), settings.PAYSTACK_SECRET_KEY):
        return HttpResponse(status=401)
    try:
        event = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)
    if event.get("event") == "charge.success":
        reference = (event.get("data") or {}).get("reference", "")
        try:
            verify_reference(reference)  # unknown references return None and are acknowledged
        except PaystackError:
            return HttpResponse(status=503)  # let Paystack retry later
        except Exception:  # noqa: BLE001
            log.exception("Webhook processing failed for %s", reference)
            return HttpResponse(status=500)
    elif event.get("event") in ("refund.processed", "refund.failed", "refund.pending", "refund.processing"):
        try:
            from apps.dashboard.services import apply_refund_event

            apply_refund_event(event["event"], event.get("data") or {})
        except Exception:  # noqa: BLE001
            log.exception("Refund webhook processing failed")
            return HttpResponse(status=500)
    return HttpResponse(status=200)
