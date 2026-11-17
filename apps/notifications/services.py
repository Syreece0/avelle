"""Notifications: customer emails (confirmed, shipped, delivered, refund, welcome), admin alerts (new order,
new customer, low or out of stock) and the dashboard's notification list.

Every event has a ``dedupe_key`` so retries and repeated saves can't create or send it twice. Email
bookkeeping rows use keys starting with ``order-email:`` and are hidden from every list (see visible_admin()).
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.db.models import Q
from django.utils import timezone

from .models import Notification

log = logging.getLogger(__name__)


def _once(**fields):
    """Create a notification unless that event was already recorded. Returns (obj, created)."""
    lookup = {"dedupe_key": fields["dedupe_key"], "recipient": fields.get("recipient")}
    return Notification.objects.get_or_create(**lookup, defaults=fields)


def notify_order_paid(order):
    link = reverse("orders:detail", args=[order.order_number])
    if order.user_id:
        _once(
            audience=Notification.Audience.CUSTOMER, recipient=order.user, kind=Notification.Kind.ORDER_CONFIRMED,
            title=f"Order {order.order_number} confirmed", message="Thank you. We've received your payment and are getting your order ready.",
            link_url=link, dedupe_key=f"order-paid:{order.order_number}",
        )
    _once(
        audience=Notification.Audience.ADMIN, recipient=None, kind=Notification.Kind.NEW_ORDER,
        title=f"New order {order.order_number}", message=f"{order.customer_name} paid ₦{order.total:,.0f} ({order.delivery_zone_name}).",
        link_url=f"/dashboard/orders/{order.order_number}/", dedupe_key=f"new-order:{order.order_number}",
    )
    # The email is guarded by its own bookkeeping row ("order-email:" keys; hidden from admin lists
    # by Phase 10) so a retried webhook never sends it twice. If sending fails the row is removed so a retry can send.
    marker, fresh = Notification.objects.get_or_create(
        dedupe_key=f"order-email:{order.order_number}", recipient=None,
        defaults=dict(audience=Notification.Audience.ADMIN, kind=Notification.Kind.ORDER_CONFIRMED,
                      title=f"Confirmation email for {order.order_number}", message="Email record", is_read=True),
    )
    if fresh:
        try:
            body = render_to_string("orders/emails/order_confirmation.txt", {"order": order, "site_url": settings.SITE_URL.rstrip("/")})
            send_mail(f"AVELLE: order {order.order_number} confirmed", body, settings.DEFAULT_FROM_EMAIL, [order.email], fail_silently=False)
        except Exception:
            marker.delete()
            raise
        Notification.objects.filter(pk=marker.pk).update(email_sent_at=timezone.now())


# ------------------------------------------------------------------ bookkeeping rows are never shown
HIDDEN_PREFIX = "order-email:"


def visible_admin():
    """Admin notifications a person should see (email bookkeeping rows excluded)."""
    return Notification.objects.filter(audience=Notification.Audience.ADMIN).exclude(dedupe_key__startswith=HIDDEN_PREFIX)


def admin_unread_count():
    return visible_admin().filter(is_read=False).count()


# ------------------------------------------------------------------ customer emails
def _email_once(tag, order_number, to, subject, template, context):
    """Send one email per (tag, order). The marker row is removed if sending fails so a retry can send."""
    marker, fresh = Notification.objects.get_or_create(
        dedupe_key=f"{HIDDEN_PREFIX}{tag}:{order_number}", recipient=None,
        defaults=dict(audience=Notification.Audience.ADMIN, kind=Notification.Kind.ORDER_STATUS,
                      title=f"Email {tag} for {order_number}", message="Email record", is_read=True),
    )
    if not fresh:
        return False
    try:
        body = render_to_string(template, {**context, "site_url": settings.SITE_URL.rstrip("/")})
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
    except Exception:
        marker.delete()
        raise
    Notification.objects.filter(pk=marker.pk).update(email_sent_at=timezone.now())
    return True


def notify_order_status(order):
    """Shipped and delivered: an in-app note for account holders and one email each. Other statuses are silent."""
    status = order.status
    if status not in ("shipped", "delivered"):
        return
    link = reverse("orders:detail", args=[order.order_number])
    if status == "shipped":
        kind, title = Notification.Kind.SHIPPED, f"Order {order.order_number} has shipped"
        message = "Your order is on its way." + (f" {order.courier} {order.tracking_number}".rstrip() if order.courier or order.tracking_number else "")
        subject, template = f"AVELLE: order {order.order_number} has shipped", "orders/emails/order_shipped.txt"
    else:
        kind, title = Notification.Kind.DELIVERED, f"Order {order.order_number} was delivered"
        message = "Your order has been delivered. We hope you love it."
        subject, template = f"AVELLE: order {order.order_number} delivered", "orders/emails/order_delivered.txt"
    if order.user_id:
        _once(audience=Notification.Audience.CUSTOMER, recipient=order.user, kind=kind, title=title, message=message,
              link_url=link, dedupe_key=f"order-{status}:{order.order_number}")
    _email_once(status, order.order_number, order.email, subject, template, {"order": order})


def notify_refund(order, refund):
    link = reverse("orders:detail", args=[order.order_number])
    if order.user_id:
        _once(audience=Notification.Audience.CUSTOMER, recipient=order.user, kind=Notification.Kind.ORDER_STATUS,
              title=f"Refund started for {order.order_number}", message=f"We've started a refund of ₦{refund.amount:,.2f}.",
              link_url=link, dedupe_key=f"refund:{refund.pk}")
    _email_once(f"refund-{refund.pk}", order.order_number, order.email, f"AVELLE: refund for order {order.order_number}",
                "orders/emails/refund_started.txt", {"order": order, "refund": refund})


def send_welcome(user):
    body = render_to_string("accounts/emails/welcome.txt", {"user": user, "site_url": settings.SITE_URL.rstrip("/")})
    send_mail("Welcome to AVELLE", body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)


# ------------------------------------------------------------------ admin alerts
def notify_new_customer(user):
    _once(audience=Notification.Audience.ADMIN, recipient=None, kind=Notification.Kind.NEW_CUSTOMER,
          title=f"New customer: {user.full_name}", message=user.email, link_url=f"/dashboard/customers/{user.pk}/",
          dedupe_key=f"new-customer:{user.pk}")


def sync_stock_alert(inventory):
    """Raise one alert when a variant becomes low or out of stock; clear it once restocked so it can fire again."""
    variant = inventory.variant
    low_key, out_key = f"stock-low:{variant.pk}", f"stock-out:{variant.pk}"
    admin = Notification.objects.filter(recipient=None)
    if not variant.is_active or inventory.quantity > inventory.low_stock_threshold:
        admin.filter(dedupe_key__in=[low_key, out_key]).delete()
        return
    if inventory.quantity == 0:
        want, drop, title, msg = out_key, low_key, "Out of stock", "has run out."
    else:
        want, drop, title, msg = low_key, out_key, "Low stock", f"has {inventory.quantity} left."
    admin.filter(dedupe_key=drop).delete()
    name = f"{variant.product.name} ({variant.size.name}, {variant.colour.name})"
    _once(audience=Notification.Audience.ADMIN, recipient=None, kind=Notification.Kind.LOW_STOCK, title=f"{title}: {name}",
          message=f"{name} {msg}", link_url=f"/dashboard/inventory/{variant.pk}/", dedupe_key=want)
