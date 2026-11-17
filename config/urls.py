"""Root URL configuration.

Each later phase adds its own include() here. Django's built-in admin is kept
at /django-admin/ for superuser emergencies only; day-to-day business
operations will live in the custom dashboard app.
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("dashboard/", include("apps.dashboard.urls")),
    path("", include("apps.content.urls")),
    path("shop/", include("apps.catalog.urls")),
    path("accounts/", include("apps.accounts.urls")),
    path("cart/", include("apps.cart.urls")),
    path("wishlist/", include("apps.wishlist.urls")),
    path("payments/", include("apps.payments.urls")),
    path("", include("apps.orders.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
