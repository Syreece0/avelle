from django.urls import path

from .views import content, customers, inventory, marketing, notifications, orders, overview, payments, products, reports, settings_views, taxonomy

app_name = "dashboard"

urlpatterns = [
    path("", overview.overview, name="overview"),
    path("search/", overview.search, name="search"),

    path("orders/", orders.orders, name="orders"),
    path("orders/<str:number>/", orders.order_detail, name="order_detail"),
    path("orders/<str:number>/status/", orders.order_status, name="order_status"),
    path("orders/<str:number>/tracking/", orders.order_tracking, name="order_tracking"),
    path("orders/<str:number>/refund/", orders.order_refund, name="order_refund"),
    path("payments/", payments.payments, name="payments"),

    path("customers/", customers.customers, name="customers"),
    path("customers/<int:pk>/", customers.customer_detail, name="customer_detail"),

    path("products/", products.products, name="products"),
    path("products/new/", products.product_edit, name="product_new"),
    path("products/<int:pk>/", products.product_edit, name="product_edit"),
    path("products/<int:pk>/images/", products.product_images, name="product_images"),
    path("products/<int:pk>/variants/add/", products.variants_create, name="variants_create"),
    path("products/<int:pk>/variants/save/", products.variants_save, name="variants_save"),
    path("products/<int:pk>/delete/", products.product_delete, name="product_delete"),

    path("categories/", taxonomy.categories, name="categories"),
    path("categories/new/", taxonomy.category_edit, name="category_new"),
    path("categories/<int:pk>/", taxonomy.category_edit, name="category_edit"),
    path("categories/<int:pk>/delete/", taxonomy.category_delete, name="category_delete"),
    path("attributes/", taxonomy.attributes, name="attributes"),
    path("attributes/<str:kind>/new/", taxonomy.attribute_edit, name="attribute_new"),
    path("attributes/<str:kind>/<int:pk>/", taxonomy.attribute_edit, name="attribute_edit"),
    path("attributes/<str:kind>/<int:pk>/delete/", taxonomy.attribute_delete, name="attribute_delete"),

    path("inventory/", inventory.inventory, name="inventory"),
    path("inventory/history/", inventory.stock_history, name="stock_history"),
    path("inventory/<int:pk>/", inventory.variant_stock, name="variant_stock"),

    path("reviews/", settings_views.reviews, name="reviews"),
    path("reviews/<int:pk>/", settings_views.review_action, name="review_action"),

    path("discounts/", marketing.discounts, name="discounts"),
    path("discounts/new/", marketing.discount_edit, name="discount_new"),
    path("discounts/<int:pk>/", marketing.discount_edit, name="discount_edit"),
    path("discounts/<int:pk>/delete/", marketing.discount_delete, name="discount_delete"),
    path("promotions/", marketing.promotions, name="promotions"),
    path("promotions/new/", marketing.promotion_edit, name="promotion_new"),
    path("promotions/<int:pk>/", marketing.promotion_edit, name="promotion_edit"),
    path("promotions/<int:pk>/delete/", marketing.promotion_delete, name="promotion_delete"),

    path("notifications/", notifications.notifications, name="notifications"),
    path("notifications/read-all/", notifications.notifications_read_all, name="notifications_read_all"),
    path("notifications/<int:pk>/read/", notifications.notification_read, name="notification_read"),

    path("reports/", reports.reports, name="reports"),

    path("newsletter/", content.newsletter, name="newsletter"),
    path("newsletter/<int:pk>/toggle/", content.newsletter_toggle, name="newsletter_toggle"),

    path("content/", content.homepage, name="content_homepage"),
    path("content/homepage/<str:key>/", content.homepage_edit, name="content_homepage_edit"),
    path("content/lookbook/", content.lookbook, name="content_lookbook"),
    path("content/lookbook/new/", content.lookbook_edit, name="content_lookbook_new"),
    path("content/lookbook/<int:pk>/", content.lookbook_edit, name="content_lookbook_edit"),
    path("content/lookbook/<int:pk>/delete/", content.lookbook_delete, name="content_lookbook_delete"),
    path("content/pages/", content.pages, name="content_pages"),
    path("content/pages/new/", content.page_edit, name="content_page_new"),
    path("content/pages/<int:pk>/", content.page_edit, name="content_page_edit"),
    path("content/pages/<int:pk>/delete/", content.page_delete, name="content_page_delete"),
    path("content/announcements/", content.announcements, name="content_announcements"),
    path("content/announcements/new/", content.announcement_edit, name="content_announcement_new"),
    path("content/announcements/<int:pk>/", content.announcement_edit, name="content_announcement_edit"),
    path("content/announcements/<int:pk>/delete/", content.announcement_delete, name="content_announcement_delete"),
    path("content/settings/", content.site_settings, name="content_settings"),

    path("delivery/", settings_views.delivery, name="delivery"),
    path("delivery/add-missing/", settings_views.delivery_add_missing, name="delivery_add_missing"),
]
