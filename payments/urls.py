from django.urls import path
from . import views
from .invoice_views import invoice_detail

urlpatterns = [
    path("invoices/<str:order_number>/", invoice_detail, name="invoice-detail"),
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
