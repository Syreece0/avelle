"""Thin Paystack client. No Django imports, so it can be tested on its own.

Amounts: Paystack works in the smallest unit (kobo). Naira amounts are converted with
to_kobo(), which rounds half-up and never touches floats.
"""
import hashlib
import hmac
from decimal import ROUND_HALF_UP, Decimal

import requests


class PaystackError(Exception):
    """Raised for any failure talking to Paystack; the message is safe to log, not to show customers."""


def to_kobo(amount):
    return int((Decimal(amount) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def verify_signature(raw_body, signature, secret):
    """Paystack signs webhook bodies with HMAC-SHA512 using the secret key."""
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha512).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


class PaystackClient:
    def __init__(self, secret_key, base_url="https://api.paystack.co", timeout=15, session=None):
        if not secret_key:
            raise PaystackError("PAYSTACK_SECRET_KEY is not configured.")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.http = session or requests.Session()
        self.headers = {"Authorization": f"Bearer {secret_key}", "Content-Type": "application/json"}

    def _call(self, method, path, **kwargs):
        try:
            response = self.http.request(method, self.base_url + path, headers=self.headers, timeout=self.timeout, **kwargs)
        except requests.RequestException as error:
            raise PaystackError(f"Could not reach Paystack: {error}") from error
        try:
            payload = response.json()
        except ValueError:
            raise PaystackError(f"Paystack returned a non-JSON response (HTTP {response.status_code}).")
        if response.status_code >= 400 or not payload.get("status"):
            raise PaystackError(f"Paystack error (HTTP {response.status_code}): {payload.get('message', 'unknown')}")
        return payload["data"]

    def initialize(self, *, email, amount, reference, callback_url, currency="NGN", metadata=None):
        body = {"email": email, "amount": to_kobo(amount), "reference": reference, "callback_url": callback_url, "currency": currency}
        if metadata:
            body["metadata"] = metadata
        data = self._call("POST", "/transaction/initialize", json=body)
        if not data.get("authorization_url"):
            raise PaystackError("Paystack did not return a payment link.")
        return data

    def verify(self, reference):
        return self._call("GET", f"/transaction/verify/{reference}")

    def refund(self, *, transaction, amount, note=""):
        """Ask Paystack to refund ``amount`` (naira) of a transaction, identified by our reference."""
        body = {"transaction": transaction, "amount": to_kobo(amount)}
        if note:
            body["merchant_note"] = note[:200]
        return self._call("POST", "/refund", json=body)
