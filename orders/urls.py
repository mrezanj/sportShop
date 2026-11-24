
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
    path("returns/", views.return_requests, name="return-requests"),
    path("returns/<int:request_id>/review/", views.review_return, name="review-return"),
    path("returns/<int:request_id>/received/", views.receive_return, name="receive-return"),
    path("<str:order_number>/discrepancies/", views.open_discrepancy, name="open-discrepancy"),
    path("discrepancies/<int:case_id>/resolve/", views.resolve_discrepancy, name="resolve-discrepancy"),
    path("<str:order_number>/", views.order_detail, name="order-detail"),
    path(
        "<str:order_number>/cancel/",
        views.cancel_order,
        name="cancel-order",
    ),
]
