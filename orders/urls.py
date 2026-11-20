from django.urls import path
from . import views

urlpatterns = [
    path("provinces/", views.list_provinces, name="provinces"),
    path("shipping-methods/", views.list_shipping_methods, name="shipping-methods"),
    path("my/", views.my_orders, name="my-orders"),
    path("", views.create_order, name="create-order"),
    path("<str:order_number>/", views.order_detail, name="order-detail"),
    path(
        "<str:order_number>/cancel/",
        views.cancel_order,
        name="cancel-order",
    ),
]
