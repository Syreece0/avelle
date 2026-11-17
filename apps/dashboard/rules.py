"""Business rules for the dashboard, kept free of Django imports so they can be tested on their own.

Anything that decides *what is allowed* (who can do what, which order status can follow which,
how much can still be refunded) lives here; services.py applies the decision to the database.
"""
from datetime import timedelta
from decimal import Decimal

# ---------------------------------------------------------------- permissions
# Roles are cumulative: staff < manager < admin.
STAFF_PERMS = frozenset({"overview", "orders", "inventory", "customers"})
MANAGER_PERMS = STAFF_PERMS | {"catalogue", "promotions", "reviews", "delivery", "payments", "reports", "content"}
ADMIN_PERMS = MANAGER_PERMS | {"refunds", "team"}

ROLE_PERMS = {"staff": STAFF_PERMS, "manager": MANAGER_PERMS, "admin": ADMIN_PERMS}


def permissions_for(role, is_superuser=False):
    """Permissions granted to a role. Superusers always get everything; customers get nothing."""
    if is_superuser:
        return ADMIN_PERMS
    return ROLE_PERMS.get(role, frozenset())


# ---------------------------------------------------------------- order status
# Paid orders are cancelled by *refunding* them (see refund rules), never by a plain status change,
# so money and stock can't drift apart.
TRANSITIONS = {
    "pending_payment": ("cancelled",),
    "paid": ("processing", "shipped"),
    "processing": ("shipped",),
    "shipped": ("delivered",),
    "delivered": (),
    "cancelled": (),
    "refunded": (),
}

# Statuses that count as real, collected sales.
REVENUE_STATUSES = ("paid", "processing", "shipped", "delivered")
# Statuses where staff still have something to do.
OPEN_STATUSES = ("paid", "processing", "shipped")
REFUNDABLE_ORDER_STATUSES = ("paid", "processing", "shipped", "delivered")


def next_statuses(status):
    return TRANSITIONS.get(status, ())


def can_transition(current, target):
    return target in TRANSITIONS.get(current, ())


# ---------------------------------------------------------------- refunds
def refundable_amount(payment_amount, refund_amounts):
    """What is still refundable on one payment. ``refund_amounts`` are non-failed refunds."""
    left = Decimal(payment_amount) - sum((Decimal(a) for a in refund_amounts), Decimal("0"))
    return max(left, Decimal("0.00"))


def refund_is_full(payment_amount, refund_amounts):
    return refundable_amount(payment_amount, refund_amounts) == Decimal("0.00")


# ---------------------------------------------------------------- reporting helpers
PERIODS = {"7": 7, "30": 30, "90": 90}
DEFAULT_PERIOD = "30"


def period_days(value):
    return PERIODS.get(str(value), PERIODS[DEFAULT_PERIOD])


def percent_change(current, previous):
    """Change versus the previous period as a percentage, or None when there is nothing to compare."""
    current, previous = Decimal(current or 0), Decimal(previous or 0)
    if previous == 0:
        return None
    return float(((current - previous) / previous * 100).quantize(Decimal("0.1")))


def fill_daily_series(rows, start_date, days):
    """Turn sparse ``{date: value}`` rows into one value for each of ``days`` consecutive days."""
    lookup = {d: Decimal(v or 0) for d, v in rows}
    return [(start_date + timedelta(days=i), lookup.get(start_date + timedelta(days=i), Decimal("0"))) for i in range(days)]


def scale_bars(series, floor_pct=2):
    """Heights as whole percentages of the largest value. Non-zero days get at least ``floor_pct`` so they stay visible."""
    top = max((v for _, v in series), default=Decimal("0"))
    out = []
    for day, value in series:
        pct = 0 if top == 0 or value == 0 else max(floor_pct, int(value / top * 100))
        out.append({"date": day, "value": value, "pct": pct})
    return out


# ---------------------------------------------------------------- discount code state
def code_state(*, is_active, starts_at, expires_at, times_used, usage_limit, now):
    """One word describing a discount code, in the order a person would care about."""
    if not is_active:
        return "inactive"
    if usage_limit is not None and times_used >= usage_limit:
        return "used up"
    if expires_at is not None and now > expires_at:
        return "expired"
    if starts_at is not None and now < starts_at:
        return "scheduled"
    return "live"


# ---------------------------------------------------------------- team safety
def can_change_access(*, actor_id, target_id, target_role, new_role, new_active, active_admins):
    """Guard rails for editing someone's role/status. Returns an error message or None."""
    if actor_id == target_id:
        return "You can't change your own access. Ask another administrator."
    losing_admin = target_role == "admin" and (new_role != "admin" or not new_active)
    if losing_admin and active_admins <= 1:
        return "At least one active administrator must remain."
    return None


# ---------------------------------------------------------------- reports
from datetime import date  # noqa: E402

MAX_RANGE_DAYS = 366


def parse_range(from_text, to_text, today, default_days=30):
    """Validated inclusive date range from query-string text. Bad, reversed or huge ranges fall back safely.

    Returns (start, end, note) where ``note`` explains any correction (or is empty).
    """
    def read(text):
        try:
            return date.fromisoformat((text or "").strip())
        except ValueError:
            return None

    start, end = read(from_text), read(to_text)
    note = ""
    if end is None or end > today:
        end = today
    if start is None:
        start = end - timedelta(days=default_days - 1)
    if start > end:
        start, end, note = end, start, "The start date was after the end date, so they were swapped."
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        start, note = end - timedelta(days=MAX_RANGE_DAYS - 1), f"Reports cover at most {MAX_RANGE_DAYS} days; the start date was moved."
    return start, end, note


def csv_safe(value):
    """Stop spreadsheet formula injection: text that starts with = + - @ (or tab/CR) is prefixed with an apostrophe.

    Real numbers are left alone so they stay numeric in Excel.
    """
    if isinstance(value, (int, float, Decimal)) or value is None:
        return "" if value is None else value
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text
