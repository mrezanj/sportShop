from django.urls import path

from .dashboard_views import (
    InventoryDocumentDetailAPIView,
    InventoryDocumentHistoryAPIView,
    InventoryDocumentListAPIView,
    InventoryLowStockAPIView,
    InventorySummaryAPIView,
    InventoryThresholdDetailAPIView,
    InventoryThresholdListAPIView,
)
from .import_views import InventoryBulkImportAPIView
from .views import (
    InventoryDocumentApproveAPIView,
    InventoryDocumentCreateAPIView,
    InventoryDocumentItemCreateAPIView,
    InventoryDocumentItemDeleteAPIView,
    InventoryDocumentRejectAPIView,
    InventoryDocumentReviewAPIView,
    InventoryDocumentSubmitAPIView,
    InventoryReportAPIView,
)

urlpatterns = [
    path("import/", InventoryBulkImportAPIView.as_view(), name="inventory-bulk-import"),
    path("reports/", InventoryReportAPIView.as_view(), name="inventory-report"),
    path("summary/", InventorySummaryAPIView.as_view(), name="inventory-summary"),
    path("low-stock/", InventoryLowStockAPIView.as_view(), name="inventory-low-stock"),
    path("thresholds/", InventoryThresholdListAPIView.as_view(), name="inventory-threshold-list"),
    path("thresholds/<int:variant_id>/", InventoryThresholdDetailAPIView.as_view(), name="inventory-threshold-detail"),
    path("documents/", InventoryDocumentListAPIView.as_view(), name="inventory-document-list"),
    path("documents/create/", InventoryDocumentCreateAPIView.as_view(), name="inventory-document-create"),
    path("documents/<int:document_id>/", InventoryDocumentDetailAPIView.as_view(), name="inventory-document-detail"),
    path("documents/<int:document_id>/history/", InventoryDocumentHistoryAPIView.as_view(), name="inventory-document-history"),
    path("documents/<int:document_id>/items/", InventoryDocumentItemCreateAPIView.as_view(), name="inventory-document-item-create"),
    path("documents/<int:document_id>/items/<int:item_id>/", InventoryDocumentItemDeleteAPIView.as_view(), name="inventory-document-item-delete"),
    path("documents/<int:document_id>/submit/", InventoryDocumentSubmitAPIView.as_view(), name="inventory-document-submit"),
    path("documents/<int:document_id>/review/", InventoryDocumentReviewAPIView.as_view(), name="inventory-document-review"),
    path("documents/<int:document_id>/reject/", InventoryDocumentRejectAPIView.as_view(), name="inventory-document-reject"),
    path("documents/<int:document_id>/approve/", InventoryDocumentApproveAPIView.as_view(), name="inventory-document-approve"),
]
