"""URL configuration for the NirikshaAI Django example project."""

from django.urls import include, path

urlpatterns = [
    path("orders/", include("orders.urls")),
]
