# AVELLE: testing guide (Phase 11)

## What has been checked, and how

| Area | Tool | Status |
|---|---|---|
| Python syntax, every file | `tools/run_checks.py` (compileall) | passes |
| URL names and argument counts in templates and code; template inheritance, includes, static files, filters, `{% load %}`; ORM field and lookup names; settings | `tools/check_project.py` | passes |
| Colour contrast of every design-token pair (WCAG AA) | `tools/contrast.py` | passes |
| Dashboard rules (roles, status transitions, refunds, reports, CSV safety) | `tests_standalone/test_dashboard_rules.py` | passes |
| Paystack client (signing, request shape, refunds) | `tests_standalone/test_paystack_client.py` | passes |
| Storefront and dashboard pages in a real browser (layout, overflow at desktop and phone width, search, filters, cart, wishlist, dialogs) | Playwright against template test servers | passes |
| Accessibility smoke scan (lang, one h1, heading order, alt text, control names, duplicate ids, landmarks, skip link, 24px targets) | Playwright | issues found were fixed |

Run the fast checks any time:

    python tools/run_checks.py

## What has NOT been run

Django itself could not be installed where this was built, so the following are written but unexecuted:

- the Django test suite (`apps/dashboard/tests.py`, others);
- real database queries, migrations, forms, signals and the views as a whole;
- real Paystack payments, refunds and webhooks; real email sending;
- the Django-rendered form attributes (aria-labels on table inputs, separate ids on the tracking form), which the browser harness cannot render.

On your machine, after generating migrations:

    python manage.py makemigrations core accounts catalog cart wishlist orders payments promotions notifications content dashboard
    python manage.py migrate
    python manage.py test

Please send me any failures. Expect some on first run, since this code has never executed.

## Manual end-to-end checklist (Paystack test keys)

1. Register a customer; confirm the welcome email (console backend is fine) and an admin notification.
2. Browse, filter, search, add a variant to the bag, change quantity, add to wishlist.
3. Checkout with a Lagos address; confirm the delivery charge is the admin-set one; apply a discount code.
4. Pay with a Paystack test card; confirm the return page shows paid, stock drops, and the order is Paid in the dashboard.
5. Replay the webhook (Paystack dashboard) and confirm nothing is double-counted.
6. Dashboard: Paid, Processing, Shipped (with courier and tracking), Delivered; confirm each customer email.
7. Refund: partial then the remainder; confirm status, stock restock option, refund email and the Paystack refund webhook.
8. Leave an order unpaid, then run `python manage.py expire_unpaid_orders --hours 0 --dry-run`, then without `--dry-run`.
9. Log in as staff, manager and admin; confirm each sees only the sidebar entries and pages allowed to their role, and that a customer gets 403 on `/dashboard/`.
10. Reports: change the date range, download each CSV and open it in a spreadsheet.
11. With the OS "reduce motion" setting on, confirm animations are off.
