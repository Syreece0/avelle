from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver

from .models import Cart
from .services import SESSION_KEY, merge_guest_cart


@receiver(user_logged_in)
def merge_cart_on_login(sender, request, user, **kwargs):
    """The session key changes at login, so the guest cart is found through the session data."""
    if request is None:
        return
    cart_id = request.session.pop(SESSION_KEY, None)
    if cart_id:
        merge_guest_cart(Cart.objects.filter(pk=cart_id, user__isnull=True).first(), user)
