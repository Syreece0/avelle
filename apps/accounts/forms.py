from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.core.cache import cache
from django.db import transaction

from apps.core.forms import StyledFormMixin
from apps.core.utils import client_ip
from apps.core.validators import validate_phone

from .models import Address, CustomerProfile

User = get_user_model()

LOGIN_MAX_FAILURES = 5
LOGIN_WINDOW = 15 * 60


class LoginForm(StyledFormMixin, AuthenticationForm):
    """Email + password, with a small throttle against password guessing."""

    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}))
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "That email and password don't match. Please try again.",
        "throttled": "Too many attempts. Please wait a few minutes or reset your password.",
    }

    def _throttle_key(self, email):
        return f"login-fail:{client_ip(self.request)}:{(email or '').lower()}"

    def clean(self):
        email = self.cleaned_data.get("username") or self.data.get("username", "")
        key = self._throttle_key(email)
        if cache.get(key, 0) >= LOGIN_MAX_FAILURES:
            raise forms.ValidationError(self.error_messages["throttled"], code="throttled")
        try:
            cleaned = super().clean()
        except forms.ValidationError:
            cache.add(key, 0, LOGIN_WINDOW)
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, LOGIN_WINDOW)
            raise
        cache.delete(key)
        return cleaned


class RegisterForm(StyledFormMixin, forms.ModelForm):
    phone = forms.CharField(label="Phone (optional)", required=False, max_length=20, validators=[validate_phone],
                            widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}))
    password1 = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
                                help_text="At least 8 characters. Avoid common passwords.")
    password2 = forms.CharField(label="Confirm password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    marketing_opt_in = forms.BooleanField(label="Send me news and offers by email", required=False)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]
        widgets = {
            "first_name": forms.TextInput(attrs={"autocomplete": "given-name"}),
            "last_name": forms.TextInput(attrs={"autocomplete": "family-name"}),
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("first_name", "last_name", "email"):
            self.fields[name].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists. Try signing in instead.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "The two passwords don't match.")
        elif p1:
            candidate = User(email=cleaned.get("email", ""), first_name=cleaned.get("first_name", ""), last_name=cleaned.get("last_name", ""))
            try:
                password_validation.validate_password(p1, candidate)
            except forms.ValidationError as error:
                self.add_error("password1", error)
        return cleaned

    @transaction.atomic
    def save(self, commit=True):
        user = User.objects.create_user(
            email=self.cleaned_data["email"], password=self.cleaned_data["password1"],
            first_name=self.cleaned_data["first_name"], last_name=self.cleaned_data["last_name"],
        )
        profile, _ = CustomerProfile.objects.get_or_create(user=user)
        profile.phone = self.cleaned_data.get("phone", "")
        profile.marketing_opt_in = self.cleaned_data.get("marketing_opt_in", False)
        profile.save()
        return user


class ProfileForm(StyledFormMixin, forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField(disabled=True, help_text="Your email is your sign-in. Contact us to change it.")
    phone = forms.CharField(label="Phone", required=False, max_length=20, validators=[validate_phone])
    marketing_opt_in = forms.BooleanField(label="Send me news and offers by email", required=False)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        profile, _ = CustomerProfile.objects.get_or_create(user=user)
        self.profile = profile
        kwargs.setdefault("initial", {}).update({
            "first_name": user.first_name, "last_name": user.last_name, "email": user.email,
            "phone": profile.phone, "marketing_opt_in": profile.marketing_opt_in,
        })
        super().__init__(*args, **kwargs)

    @transaction.atomic
    def save(self):
        self.user.first_name = self.cleaned_data["first_name"]
        self.user.last_name = self.cleaned_data["last_name"]
        self.user.save(update_fields=["first_name", "last_name"])
        self.profile.phone = self.cleaned_data["phone"]
        self.profile.marketing_opt_in = self.cleaned_data["marketing_opt_in"]
        self.profile.save()


class AddressForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Address
        fields = ["label", "recipient_name", "phone", "line1", "line2", "city", "state", "landmark", "is_default"]
        labels = {"line1": "Address", "line2": "Apartment, suite, etc. (optional)", "is_default": "Use as my default address",
                  "label": "Label (optional)", "landmark": "Nearest landmark (optional)"}
        widgets = {"phone": forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
                   "recipient_name": forms.TextInput(attrs={"autocomplete": "name"}),
                   "line1": forms.TextInput(attrs={"autocomplete": "address-line1"}),
                   "line2": forms.TextInput(attrs={"autocomplete": "address-line2"}),
                   "city": forms.TextInput(attrs={"autocomplete": "address-level2"})}

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["phone"].validators.append(validate_phone)

    @transaction.atomic
    def save(self, commit=True):
        address = super().save(commit=False)
        address.user = self.user
        first = not Address.objects.filter(user=self.user).exclude(pk=address.pk).exists()
        if first:
            address.is_default = True
        if address.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(pk=address.pk).update(is_default=False)
        address.save()
        return address


class StyledPasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    pass


class StyledPasswordResetForm(StyledFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(StyledFormMixin, SetPasswordForm):
    pass
