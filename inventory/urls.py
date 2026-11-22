from django.urls import path
from .views import (
    InventoryDocumentCreateAPIView,
    InventoryReportAPIView,
)
from .views import (
    InventoryDocumentCreateAPIView,
    InventoryDocumentItemCreateAPIView,
    InventoryReportAPIView,
    InventoryDocumentSubmitAPIView,
    InventoryDocumentReviewAPIView,
    InventoryDocumentRejectAPIView,
    InventoryDocumentApproveAPIView,
)

urlpatterns = [
    path(
        "reports/",
        InventoryReportAPIView.as_view(),
        name="inventory-report",
    ),
    path(
        "documents/",
        InventoryDocumentCreateAPIView.as_view(),
        name="inventory-document-create",
    ),
    path(
        "documents/<int:document_id>/items/",
        InventoryDocumentItemCreateAPIView.as_view(),
        name="inventory-document-item-create",
    ),
    path(
        "documents/<int:document_id>/submit/",
        InventoryDocumentSubmitAPIView.as_view(),
        name="inventory-document-submit",
    ),
    path(
        "documents/<int:document_id>/review/",
        InventoryDocumentReviewAPIView.as_view(),
        name="inventory-document-review",
    ),
    path(
        "documents/<int:document_id>/reject/",
        InventoryDocumentRejectAPIView.as_view(),
        name="inventory-document-reject",
    ),
    path(
        "documents/<int:document_id>/approve/",
        InventoryDocumentApproveAPIView.as_view(),
        name="inventory-document-approve",
    ),
]
