from django.urls import path

from .views import InventoryReportAPIView


urlpatterns = [
    path(
        "reports/",
        InventoryReportAPIView.as_view(),
        name="inventory-report",
    ),
]