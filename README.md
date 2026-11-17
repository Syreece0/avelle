# AVELLE

Luxury fashion e-commerce platform (Django 5.2 LTS, PostgreSQL, vanilla JS, GSAP, Cloudinary, Paystack, Render).

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # then edit values
createdb avelle                                       # or create the database in pgAdmin
python manage.py makemigrations core accounts catalog cart wishlist orders payments promotions notifications content dashboard
python manage.py migrate
python manage.py seed_initial_data
python manage.py createsuperuser
python manage.py runserver
```

`makemigrations` must list `accounts` first so the custom user model exists before anything references it.

## Style guides (Phase 3)

With the dev server running, open:

- http://127.0.0.1:8000/static/design-system/index.html  (storefront design system, live components)
- http://127.0.0.1:8000/static/design-system/dashboard.html  (dashboard design system)

All header links now work.

## Homepage and demo data (Phase 4)

```powershell
python manage.py seed_initial_data      # categories, sizes, colours, delivery zones, page stubs (safe to re-run)
python manage.py seed_demo_catalog      # 15 demo products with generated images, hero, editorial, promotions
python manage.py runserver
```

Open http://127.0.0.1:8000/. Remove the demo products and promotions any time with
`python manage.py seed_demo_catalog --clear`. Demo images are generated placeholders marked "DEMO IMAGE".

Homepage content keys (Website Content in the dashboard, Phase 10): `hero`, `intro`, `editorial`, `editorial-detail`.
Hero title lines are separated with a vertical bar, e.g. `Dressed in|quiet confidence`.

GSAP and ScrollTrigger load from cdnjs. If they are blocked, or the visitor prefers reduced motion, the page is fully visible and static.

## Status

- Phase 2: skeleton and database models (complete, tested locally)
- Phase 3: design system (complete)
- Phase 4: homepage (complete)
- Phase 5: shop, filters, search, product page (complete)
- Phase 6: animation system (complete)
- Phase 7: accounts, wishlist, bag (complete)
- Phase 8: checkout, orders, Paystack
- Phases 9–10: dashboard, notifications, reports, content (complete)
- Phase 11: testing tools and guide (complete)

## Shop and product pages (Phase 5)

- `/shop/` listing with category tabs, type pills, filters (size, colour, brand, price, in stock, new, sale, featured), sorting and load-more. Filters apply without a page reload and the URL always reflects them; with JavaScript off, the same page works as ordinary links and an Apply button.
- `/shop/products/<slug>/` product page: gallery, lightbox, colour/size picker with stock messages, size guide, reviews (display only), related products.
- `/shop/suggest/` powers the header search suggestions.
- Stand-ins until Phase 7: the wishlist heart and "Add to bag" show a short notice instead of saving. Both are wired to `window.Avelle.wishlistToggle` / `window.Avelle.addToCart`, which Phase 7 will define.
- Phase 6 hooks: `avelle:results-leaving` and `avelle:results-rendered` (see top of `static/js/shop.js`).

## Animation system (Phase 6)

All motion lives in `static/js/motion.js` (plus the hero intro in `home.js`). GSAP and ScrollTrigger load from cdnjs on every page; if they are blocked, or the visitor prefers reduced motion, everything stays visible and static.

- Card entrance direction is set per grid: `<ul class="product-grid" data-enter="up|left|right|mixed">`. `mixed` sends the left column in from the left, the right column in from the right and the rest up from below.
- Floating and 3D tilt are desktop-only; phones get entrances and reveals only. Floating pauses for cards off screen and slows while one is hovered.
- Reveals: `data-reveal="up|left|right"`. Parallax: `data-parallax` / `data-parallax-inner` (desktop).
- Shop filtering plays an exit, then the new cards enter (via the `avelle:results-*` events).
- Pages fade between internal links; add `data-no-transition` to a link to opt out.
- Tuning knobs (distance, duration, stagger, float on/off) are the `DESKTOP` and `MOBILE` objects at the top of `motion.js`.

## Accounts, wishlist and bag (Phase 7)

No new models, so no new migrations. Try it:

1. `/accounts/register/` to create a customer, then `/accounts/` for details, addresses and password.
2. Add items as a guest, then sign in: the guest bag is merged into your account's bag (stock limits respected).
3. Hearts need an account; guests are offered a sign-in link. `/wishlist/` lists saved pieces.
4. Password reset prints the email to the terminal in development.

Rules worth knowing: a bag line is one variant (size + colour), capped by stock and 10 per line; prices are read live, never stored in the bag; unavailable lines stay visible and block checkout until removed; five failed sign-ins for the same email and address pause attempts for 15 minutes.
Not yet built: email verification (the field exists), the Orders page and checkout (Phase 8).

## Checkout, orders and Paystack (Phase 8)

Guests and signed-in customers can check out. Delivery is charged by state from the Delivery Zone table (`seed_initial_data` creates placeholder charges; the dashboard will edit them in Phase 9).

Set these in `.env` (use Paystack **test** keys first):

```
PAYSTACK_SECRET_KEY=sk_test_...
SITE_URL=http://localhost:8000
```

How a payment flows: checkout creates an order as *pending payment* (stock is not taken yet) and sends the customer to Paystack. When they return to `/payments/callback/`, the server asks Paystack for the real result (it never trusts the browser), checks the amount, then marks the order paid, takes stock (written to the stock history), redeems the discount code and emails the confirmation, once only. Paystack's webhook (`/payments/webhook/`, signed) does the same job in case the customer closes the tab; whichever arrives first wins and the other is a no-op.

In the Paystack dashboard (Settings, API Keys and Webhooks) set the webhook URL to `https://<your-domain>/payments/webhook/`. On your own computer Paystack can't reach localhost, so the webhook won't fire there; the callback alone still completes the order. Test card numbers are in Paystack's docs.

Edge cases handled: abandoned payments can be retried from the order page; a second successful charge for an already-paid order is recorded as "refund required" instead of a second sale; if stock ran out between checkout and payment, the order is still marked paid and a "STOCK SHORTFALL" note appears in its history for staff (hidden from the customer's view).
Not built yet: expiring old unpaid orders, refunds from the dashboard (Phase 9), shipping emails (Phase 10).

## Phase 9: Administrator dashboard (`/dashboard/`)

A business interface that is separate from Django admin (which stays at `/django-admin/` for emergencies).

**Getting in.** Create a user with role Staff, Manager or Administrator (a superuser counts as Administrator), sign in at `/accounts/login/`: dashboard users land on `/dashboard/` unless they were heading elsewhere. A "Dashboard" link also appears in their account menu.

| Role | Can use |
|------|---------|
| Staff | Overview, orders (status, tracking), inventory and stock adjustments, customers (view) |
| Manager | + products, images, variants, categories, brands/sizes/colours, reviews, discount codes, promotions, delivery charges, payments (view) |
| Administrator | + refunds, changing anyone's role or deactivating accounts |

The rules live in `apps/dashboard/rules.py`. Anyone else gets a 403; signed-out visitors go to sign-in.

**Overview.** Every figure is a database query (`apps/dashboard/stats.py`): revenue, orders, average order, units sold and new customers for 7/30/90 days with the change against the previous period of equal length; revenue by day; orders by status; best sellers; low stock; recent orders; and a "needs your attention" list (paid orders to fulfil, STOCK SHORTFALL notes, duplicate payments needing refunds, low stock, reviews awaiting approval). *Revenue* means orders that are paid and not refunded or cancelled, counted on the day payment arrived.

**Orders.** Search and status tabs; the detail page shows items, totals, payments, refunds and the full history. Status moves follow fixed rules: paid → processing/shipped → delivered; an unpaid order can be cancelled. Paid orders are cancelled by *refunding* them, so money and stock can't drift apart. Shipping records courier and tracking, which the customer sees on their order timeline.

**Refunds** (administrators): up to the unrefunded balance of the successful payment, sent to Paystack `POST /refund`. The refund row is saved before the call, a failed call is marked failed and frees the amount, and a full refund marks the order refunded and can return exactly what that order took from stock. Paystack's `refund.processed` / `refund.failed` webhook events update the refund (same webhook URL as payments).

**Catalogue.** Products (search, filters, stock), images (multi-upload, main image, colour link), variants (generate size × colour combinations with opening stock; variants are switched off, never deleted, so history stays intact), categories, brands, sizes, colours. **Inventory**: every change is a logged adjustment (restock, return, damaged, stock count) and can never go below zero; a stock-history page lists all movements. **Marketing**: discount codes (percentage or fixed, limits, schedule; used codes are switched off, not deleted) and homepage promotion banners. **Delivery charges**: one page for all states (charge, free-delivery threshold, estimated days, on/off), with a button to add any missing Nigerian states switched off.

**Not in this phase** (Phase 10): notification centre and shipping emails, reports/exports, editing homepage and page content, expiring unpaid orders.

**Tests.** `python tests_standalone/test_dashboard_rules.py` and `test_paystack_client.py` run without Django. `python manage.py test apps.dashboard` runs the Django tests (access control, KPI numbers, status rules, stock, refunds with a mocked Paystack client, team guard rails). Those were written but not run in the sandbox that built this project.

## Phase 10: Notifications, reports, content (dashboard)

**Customer emails.** Confirmed (Phase 8), shipped (with courier and tracking), delivered, refund started, and a welcome email on registration. Each is sent once per event: a hidden bookkeeping row (`order-email:...`) guards it, is removed if sending fails so a retry can send, and is never shown in any list. A failing mail server never blocks a payment, status change or refund. In development emails print to the terminal; for production set the `EMAIL_*` settings (SMTP) and `DEFAULT_FROM_EMAIL`.

**Admin notifications** (`/dashboard/notifications/`, bell in the top bar): new orders, new customers, and low or out-of-stock alerts. Stock alerts come from a signal on Inventory, so every path that changes stock (sales, dashboard adjustments) raises them. One alert per variant: it is replaced when low becomes out, and cleared when restocked so it can fire again. Read state is shared across the team.

**Reports** (`/dashboard/reports/`, managers and administrators): Sales (one row per paid order), Products, Customers, Delivery states, and Stock (valued at selling price), each with a date range (up to 366 days; bad dates fall back safely) and a CSV download that contains every row. CSV cells that start with `= + - @` are prefixed so spreadsheets can't run them as formulas.

**Website content** (`/dashboard/content/`): the four homepage blocks (hero, intro, brand story, detail image; unset blocks use the built-in defaults), information pages (create, edit, publish, delete), the announcement bar, and contact details and social links. **Newsletter** (`/dashboard/newsletter/`): subscribers list, manual unsubscribe/resubscribe, CSV download.

**Expiring unpaid orders.** `python manage.py expire_unpaid_orders [--hours 48] [--dry-run]` cancels orders left unpaid longer than the limit. It first re-checks each unfinished payment with Paystack and completes the order if the customer did pay; if Paystack can't be reached the order is left for the next run. On Render, add a Cron Job running it once a day.

**Tests.** Standalone: `python tests_standalone/test_dashboard_rules.py` (now also covers report date ranges and CSV safety). Django: `python manage.py test apps.dashboard` has new classes for stock alerts, emails, notifications, reports, content and expiry. As in Phase 9 these were written but not run in the sandbox that built this project.


## Phase 11: testing

See `TESTING.md`. `python tools/run_checks.py` runs the static project checker, contrast checks and the standalone tests. The Django test suite and live Paystack/email flows still need to be run on your machine.

## Light glass theme

`static/css/glass.css` (loaded last on the storefront and dashboard) restyles the site as frosted glass in the same ivory/champagne/ink/gold palette: translucent panels with light edges, a soft glow behind the page, glossy buttons, a dark-glass dashboard sidebar. Backdrop blur is used only on large surfaces for performance, and it falls back to solid colours when the browser lacks `backdrop-filter` or the visitor asks for reduced transparency or more contrast. To tune it, edit the `--glass-*` tokens at the top of that file; to remove it, delete the two `<link>` lines in `templates/base.html` and `templates/dashboard/base.html`.

## Lookbook carousel hero

Dashboard > Website content > **Lookbook**: choose "Lookbook carousel" as the hero style and add 3-10 slides
(image, headline, subheadline, button text, and a product or any link). Each picture's words and button appear
only while it is at the front; it holds 5 seconds, then the ring turns one card. The ring leans toward the cursor.
With fewer than 3 active slides the normal hero is shown. Portrait images (about 4:5) work best.
After pulling this change run `python manage.py makemigrations content catalog promotions && python manage.py migrate`.
