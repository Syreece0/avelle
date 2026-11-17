from django import forms

from apps.core.forms import StyledFormMixin
from apps.core.validators import validate_phone

from .models import DeliveryZone


class CheckoutForm(StyledFormMixin, forms.Form):
    email = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    customer_name = forms.CharField(label="Full name", max_length=150, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    phone = forms.CharField(label="Phone", max_length=20, validators=[validate_phone], widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}))
    address_line1 = forms.CharField(label="Address", max_length=255, widget=forms.TextInput(attrs={"autocomplete": "address-line1"}))
    address_line2 = forms.CharField(label="Apartment, suite, etc. (optional)", max_length=255, required=False, widget=forms.TextInput(attrs={"autocomplete": "address-line2"}))
    city = forms.CharField(label="City", max_length=100, widget=forms.TextInput(attrs={"autocomplete": "address-level2"}))
    state = forms.ChoiceField(label="State")
    landmark = forms.CharField(label="Nearest landmark (optional)", max_length=255, required=False)
    delivery_note = forms.CharField(label="Delivery note (optional)", max_length=255, required=False)
    discount_code = forms.CharField(label="Discount code", max_length=40, required=False)
    save_address = forms.BooleanField(label="Save this address to my account", required=False)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        states = list(DeliveryZone.objects.filter(is_active=True).order_by("state").values_list("state", flat=True))
        self.fields["state"].choices = [("", "Choose your state")] + [(s, s) for s in states]
        self.user = user
        self.fields["discount_code"].widget.attrs.update({"autocomplete": "off", "aria-label": "Discount code", "placeholder": "Enter code"})

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()
