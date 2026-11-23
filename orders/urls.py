
from django.urls import path

from . import views
from .shipping_preview import shipping_preview

urlpatterns = [
    path("provinces/", views.list_provinces, name="provinces"),
    path(
        "shipping-methods/",
        views.list_shipping_methods,
        name="shipping-methods",
    ),
    path(
        "shipping-preview/",
        shipping_preview,
        name="shipping-preview",
    ),
    path("my/", views.my_orders, name="my-orders"),
    path("", views.create_order, name="create-order"),
    path("<str:order_number>/", views.order_detail, name="order-detail"),
    path(
        "<str:order_number>/cancel/",
        views.cancel_order,
        name="cancel-order",
    ),
]
