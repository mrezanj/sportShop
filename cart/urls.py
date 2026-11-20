from django.urls import path
from . import views

urlpatterns = [
    path("", views.cart_detail, name="cart-detail"),
    path("items/", views.add_cart_item, name="cart-add-item"),
    path(
        "items/<int:item_id>/",
        views.update_cart_item,
        name="cart-update-item",
    ),
    path(
        "items/<int:item_id>/remove/",
        views.remove_cart_item,
        name="cart-remove-item",
    ),
    path("checkout/", views.checkout, name="cart-checkout"),
    path("clear/", views.clear_cart, name="cart-clear"),
]
