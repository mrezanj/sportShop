from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Brand, Category, Product, ProductVariant
from .models import InventoryBatch, InventoryDocument, InventoryDocumentItem, InventoryMovement


class InventoryBulkImportAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="bulk_inventory_user", password="test-pass")
        permission = Permission.objects.get(codename="can_create_inventory_document")
        self.user.user_permissions.add(permission)
        brand = Brand.objects.create(name="Bulk Brand", slug="bulk-brand")
        category = Category.objects.create(name="Bulk Category", slug="bulk-category")
        product = Product.objects.create(
            name_fa="Bulk Product",
            slug="bulk-product",
            brand=brand,
            category=category,
            description="Test",
        )
        self.variant = ProductVariant.objects.create(
            product=product, price=1000, stock=0, sku="BULK-001"
        )
        self.other_variant = ProductVariant.objects.create(
            product=product, price=2000, stock=0, sku="BULK-002",
            flavor="Vanilla",
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def upload(self, content, name="inventory.csv"):
        return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")

    def post_import(self, content, document_number="BULK-DOC-001"):
        return self.client.post(
            "/api/inventory/import/",
            {
                "document_number": document_number,
                "reference": "SUPPLIER-REF",
                "reason": "Bulk receipt",
                "file": self.upload(content),
            },
            format="multipart",
        )

    def test_csv_import_creates_one_draft_document_with_multiple_batch_rows(self):
        response = self.post_import(
            "sku,quantity,batch_number,expiration_date,unit_cost,reason\n"
            "BULK-001,5,BATCH-A,2030-01-01,100000,First lot\n"
            "BULK-001,7,BATCH-B,2030-06-01,110000,Second lot\n"
            "BULK-002,3,BATCH-C,,90000,Third lot\n"
        )
        self.assertEqual(response.status_code, 201)
        document = InventoryDocument.objects.get(pk=response.data["document_id"])
        self.assertEqual(document.status, "draft")
        self.assertEqual(document.document_type, "purchase")
        self.assertEqual(document.items.count(), 3)
        self.assertEqual(InventoryDocumentItem.objects.filter(document=document).count(), 3)
        self.assertEqual(InventoryMovement.objects.filter(document=document).count(), 0)
        self.assertEqual(InventoryBatch.objects.count(), 0)
        self.assertEqual(response.data["rows_processed"], 3)

    def test_invalid_later_row_creates_no_document_or_items(self):
        response = self.post_import(
            "sku,quantity,batch_number\n"
            "BULK-001,5,BATCH-A\n"
            "UNKNOWN-SKU,2,BATCH-B\n"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(InventoryDocument.objects.count(), 0)
        self.assertEqual(InventoryDocumentItem.objects.count(), 0)

    def test_duplicate_sku_and_batch_in_file_is_rejected(self):
        response = self.post_import(
            "sku,quantity,batch_number\n"
            "BULK-001,5,BATCH-A\n"
            "BULK-001,2,BATCH-A\n"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(InventoryDocument.objects.count(), 0)

    def test_expired_batch_date_is_rejected(self):
        yesterday = (timezone.localdate() - timedelta(days=1)).isoformat()
        response = self.post_import(
            f"sku,quantity,batch_number,expiration_date\nBULK-001,5,BATCH-A,{yesterday}\n"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(InventoryDocument.objects.count(), 0)

    def test_existing_batch_is_reused_without_creating_duplicate(self):
        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="EXISTING-BATCH",
            expiration_date=timezone.localdate() + timedelta(days=30),
            created_by=self.user,
        )
        response = self.post_import(
            f"sku,quantity,batch_number,expiration_date\n"
            f"BULK-001,4,EXISTING-BATCH,{batch.expiration_date.isoformat()}\n"
            ,
            document_number="BULK-DOC-EXISTING",
        )
        self.assertEqual(response.status_code, 201)
        item = InventoryDocumentItem.objects.get(document_id=response.data["document_id"])
        self.assertEqual(item.batch_id, batch.id)
        self.assertEqual(item.new_batch_number, "")
        self.assertEqual(InventoryBatch.objects.count(), 1)

    def test_import_requires_inventory_document_permission(self):
        self.user.user_permissions.clear()
        response = self.post_import(
            "sku,quantity,batch_number\nBULK-001,5,BATCH-A\n",
            document_number="BULK-DOC-DENIED",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(InventoryDocument.objects.count(), 0)

    def test_xlsx_import_is_supported(self):
        from io import BytesIO
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["sku", "quantity", "batch_number", "expiration_date"])
        sheet.append(["BULK-001", 8, "XLSX-BATCH", "2031-01-01"])
        buffer = BytesIO()
        workbook.save(buffer)
        file = SimpleUploadedFile(
            "inventory.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response = self.client.post(
            "/api/inventory/import/",
            {"document_number": "BULK-DOC-XLSX", "file": file},
            format="multipart",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["rows_processed"], 1)


    def test_csv_rejects_extra_nonempty_cells_without_creating_document(self):
        response = self.post_import(
            "sku,quantity,batch_number\n"
            "BULK-001,5,BATCH-A,UNEXPECTED\n"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(InventoryDocument.objects.count(), 0)

    def test_csv_rejects_blank_or_duplicate_headers(self):
        for content, number in (
            ("sku,quantity,batch_number,\nBULK-001,5,BATCH-A,\n", "BULK-DOC-BLANK-HEADER"),
            ("sku,quantity,sku,batch_number\nBULK-001,5,BULK-001,BATCH-A\n", "BULK-DOC-DUP-HEADER"),
        ):
            response = self.post_import(content, document_number=number)
            self.assertEqual(response.status_code, 400)
        self.assertEqual(InventoryDocument.objects.count(), 0)

    def test_csv_rejects_more_than_5000_data_rows(self):
        lines = ["sku,quantity,batch_number"]
        lines.extend(f"BULK-001,1,BATCH-{index}" for index in range(5001))
        response = self.post_import("\n".join(lines) + "\n", document_number="BULK-DOC-TOO-MANY")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(InventoryDocument.objects.count(), 0)

    def test_import_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.post_import(
            "sku,quantity,batch_number\nBULK-001,5,BATCH-A\n",
            document_number="BULK-DOC-UNAUTHENTICATED",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(InventoryDocument.objects.count(), 0)
