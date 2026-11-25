from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.utils import timezone

from rest_framework.test import APIClient

from catalog.models import Brand, Category, Product, ProductVariant

from .models import (
    InventoryBatch,
    InventoryDocument,
    InventoryDocumentItem,
    InventoryMovement,
)


class InventoryReportsAPITests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(
            username="inventory-report-viewer",
            password="test-pass",
        )
        self.viewer.user_permissions.add(
            Permission.objects.get(codename="can_view_inventory_reports")
        )
        self.customer = User.objects.create_user(
            username="inventory-report-customer",
            password="test-pass",
        )

        brand = Brand.objects.create(
            name="Report Brand",
            slug="report-brand",
        )
        category = Category.objects.create(
            name="Report Category",
            slug="report-category",
        )
        product = Product.objects.create(
            name_fa="محصول گزارش انبار",
            slug="inventory-report-product",
            brand=brand,
            category=category,
            description="Inventory report test",
        )
        variant = ProductVariant.objects.create(
            product=product,
            price=1000,
            stock=0,
            sku="REPORT-001",
        )
        self.batch = InventoryBatch.objects.create(
            variant=variant,
            batch_number="REPORT-BATCH-001",
            expiration_date=timezone.localdate() + timedelta(days=30),
            created_by=self.viewer,
        )
        document = InventoryDocument.objects.create(
            document_number="REPORT-DOC-001",
            document_type="purchase",
            created_by=self.viewer,
            reason="Inventory report test",
        )
        item = InventoryDocumentItem.objects.create(
            document=document,
            variant=variant,
            batch=self.batch,
            quantity=7,
            direction="inbound",
            unit_cost=150000,
        )
        self.movement = InventoryMovement.objects.create(
            batch=self.batch,
            document=document,
            document_item=item,
            movement_type="inbound",
            quantity_delta=7,
            created_by=self.viewer,
            notes="Initial report movement",
        )
        self.client = APIClient()

    def test_customer_cannot_view_batch_or_movement_reports(self):
        self.client.force_authenticate(self.customer)

        batches = self.client.get("/api/inventory/reports/batches/")
        movements = self.client.get("/api/inventory/reports/movements/")

        self.assertEqual(batches.status_code, 403)
        self.assertEqual(movements.status_code, 403)

    def test_report_permission_can_view_batch_quantities(self):
        self.client.force_authenticate(self.viewer)

        response = self.client.get("/api/inventory/reports/batches/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["sku"], "REPORT-001")
        self.assertEqual(row["batch_number"], "REPORT-BATCH-001")
        self.assertEqual(row["physical"], 7)
        self.assertEqual(row["reserved"], 0)
        self.assertEqual(row["available"], 7)
        self.assertFalse(row["is_expired"])

    def test_batch_report_search_and_status_validation(self):
        self.client.force_authenticate(self.viewer)

        found = self.client.get(
            "/api/inventory/reports/batches/?search=REPORT-BATCH"
        )
        missing = self.client.get(
            "/api/inventory/reports/batches/?search=NOT-FOUND"
        )
        invalid = self.client.get(
            "/api/inventory/reports/batches/?status=unknown"
        )

        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.data["count"], 1)
        self.assertEqual(missing.status_code, 200)
        self.assertEqual(missing.data["count"], 0)
        self.assertEqual(invalid.status_code, 400)

    def test_movement_report_contains_document_batch_and_unit_cost(self):
        self.client.force_authenticate(self.viewer)

        response = self.client.get("/api/inventory/reports/movements/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["sku"], "REPORT-001")
        self.assertEqual(row["batch_number"], "REPORT-BATCH-001")
        self.assertEqual(row["movement_type"], "inbound")
        self.assertEqual(row["quantity_delta"], 7)
        self.assertEqual(row["document_number"], "REPORT-DOC-001")
        self.assertEqual(row["document_item_id"], self.movement.document_item_id)
        self.assertEqual(str(row["unit_cost"]), "150000")

    def test_movement_report_filters_and_validates(self):
        self.client.force_authenticate(self.viewer)

        found = self.client.get(
            "/api/inventory/reports/movements/?document_number=REPORT-DOC"
        )
        invalid_type = self.client.get(
            "/api/inventory/reports/movements/?movement_type=unknown"
        )
        invalid_batch = self.client.get(
            "/api/inventory/reports/movements/?batch_id=invalid"
        )
        invalid_date = self.client.get(
            "/api/inventory/reports/movements/?from_date=not-a-date"
        )
        reversed_dates = self.client.get(
            "/api/inventory/reports/movements/"
            "?from_date=2026-12-01&to_date=2026-11-01"
        )

        self.assertEqual(found.status_code, 200)
        self.assertEqual(found.data["count"], 1)
        self.assertEqual(invalid_type.status_code, 400)
        self.assertEqual(invalid_batch.status_code, 400)
        self.assertEqual(invalid_date.status_code, 400)
        self.assertEqual(reversed_dates.status_code, 400)
