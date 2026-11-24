from django.urls import path
from . import views

urlpatterns = [
    path("refunds/", views.create_refund, name="create-refund"),
    path("refunds/<int:refund_id>/transition/", views.transition_refund, name="transition-refund"),
    path("initiate/", views.initiate_payment, name="initiate-payment"),
    path("verify/", views.verify_payment, name="verify-payment"),
    path("recover/", views.recover_payment, name="recover-payment"),
    path(
        "mock/<int:payment_id>/",
        views.mock_payment_page,
        name="mock-payment-page",
    ),
]
