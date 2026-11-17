from django.urls import path

from . import views

app_name = "orders"

urlpatterns = [
    path("checkout/", views.checkout, name="checkout"),
    path("checkout/quote/", views.quote_json, name="quote"),
    path("orders/", views.order_list, name="list"),
    path("orders/<str:number>/", views.order_detail, name="detail"),
    path("orders/<str:number>/pay/", views.pay_again, name="pay"),
]
