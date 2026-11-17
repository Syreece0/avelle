from django.urls import path

from . import views

app_name = "catalog"

urlpatterns = [
    path("", views.shop, name="shop"),
    path("suggest/", views.suggest_view, name="suggest"),
    path("products/<slug:slug>/", views.product_detail, name="product"),
]
