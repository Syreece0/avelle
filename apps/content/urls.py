from django.urls import path

from . import views

app_name = "content"

urlpatterns = [
    path("newsletter/subscribe/", views.newsletter_subscribe, name="newsletter_subscribe"),
    path("pages/<slug:key>/", views.info_page, name="page"),
]
