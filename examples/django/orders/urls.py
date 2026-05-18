"""URL patterns for the orders app."""

from django.urls import path

from orders import views

urlpatterns = [
    path("", views.list_orders, name="orders-list"),
    path("<str:order_id>/", views.order_detail, name="orders-detail"),
]
