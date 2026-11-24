from datetime import timedelta

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import Brand, Category, Product, ProductVariant
from .models import InventoryBatch, InventoryDocument, InventoryDocumentItem, InventoryDocumentLog, InventoryStockThreshold


class InventoryDashboardAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="dashboard_user", password="test-pass")
        self.manager = User.objects.create_user(username="dashboard_manager", password="test-pass")
        permission = Permission.objects.get(codename="can_view_inventory_reports")
        self.user.user_permissions.add(permission)
        manager_permission = Permission.objects.get(codename="can_approve_inventory_document")
        self.manager.user_permissions.add(manager_permission)

        self.brand = Brand.objects.create(name="Dashboard Brand", slug="dashboard-brand")
        self.category = Category.objects.create(name="Dashboard Category", slug="dashboard-category")
        self.product = Product.objects.create(
            name_fa="Dashboard Product",
            slug="dashboard-product",
            brand=self.brand,
            category=self.category,
            description="Test",
        )
        self.variant = ProductVariant.objects.create(
            product=self.product, price=1000, stock=0, sku="DASH-001"
        )
        self.batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="DASH-BATCH-001",
            expiration_date=timezone.localdate() + timedelta(days=30),
            created_by=self.user,
        )
        self.document = InventoryDocument.objects.create(
            document_number="DASH-DOC-001",
            document_type="inbound",
            created_by=self.user,
            reason="Dashboard test",
        )
        self.item = InventoryDocumentItem.objects.create(
            document=self.document,
            variant=self.variant,
            batch=self.batch,
            quantity=5,
            direction="inbound",
        )
        self.client = APIClient()

    def test_document_create_endpoint_remains_backward_compatible(self):
        creator_permission = Permission.objects.get(codename="can_create_inventory_document")
        self.user.user_permissions.add(creator_permission)
        self.client.force_authenticate(self.user)
        response = self.client.post(
            "/api/inventory/documents/",
            {
                "document_number": "DASH-CREATED-001",
                "document_type": "inbound",
                "reason": "Compatibility test",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["document_number"], "DASH-CREATED-001")

    def test_document_list_requires_inventory_permission(self):
        denied = User.objects.create_user(username="no_inventory", password="test-pass")
        self.client.force_authenticate(denied)
        response = self.client.get("/api/inventory/documents/")
        self.assertEqual(response.status_code, 403)

    def test_document_list_filter_and_search(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/inventory/documents/?status=draft&search=DASH-DOC")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["document_number"], "DASH-DOC-001")

    def test_document_list_rejects_invalid_filter(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/inventory/documents/?status=unknown")
        self.assertEqual(response.status_code, 400)

    def test_document_detail_contains_safe_item_data(self):
        self.client.force_authenticate(self.user)
        response = self.client.get(f"/api/inventory/documents/{self.document.id}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"][0]["sku"], "DASH-001")
        self.assertEqual(response.data["items"][0]["quantity"], 5)
        self.assertNotIn("password", response.data)

    def test_document_history_returns_immutable_log_entries(self):
        InventoryDocumentLog.objects.create(
            document=self.document,
            action="created",
            actor=self.user,
            from_status="",
            to_status="draft",
        )
        self.client.force_authenticate(self.user)
        response = self.client.get(f"/api/inventory/documents/{self.document.id}/history/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["actor_username"], self.user.username)

    def test_threshold_update_is_manager_only(self):
        self.client.force_authenticate(self.user)
        denied = self.client.put(
            f"/api/inventory/thresholds/{self.variant.id}/",
            {"minimum_quantity": 4},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)

        self.client.force_authenticate(self.manager)
        allowed = self.client.put(
            f"/api/inventory/thresholds/{self.variant.id}/",
            {"minimum_quantity": 4},
            format="json",
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.data["minimum_quantity"], 4)
        self.assertEqual(
            InventoryStockThreshold.objects.get(variant=self.variant).updated_by,
            self.manager,
        )

    def test_threshold_update_rejects_negative_or_boolean(self):
        self.client.force_authenticate(self.manager)
        for value in (-1, True, "4"):
            response = self.client.put(
                f"/api/inventory/thresholds/{self.variant.id}/",
                {"minimum_quantity": value},
                format="json",
            )
            self.assertEqual(response.status_code, 400)

    def test_summary_and_low_stock_use_ledger_inventory(self):
        self.client.force_authenticate(self.user)
        summary = self.client.get("/api/inventory/summary/")
        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.data["sku_count"], 1)
        self.assertEqual(summary.data["physical_quantity"], 0)

        InventoryStockThreshold.objects.create(
            variant=self.variant, minimum_quantity=3, updated_by=self.manager
        )
        low_stock = self.client.get("/api/inventory/low-stock/")
        self.assertEqual(low_stock.status_code, 200)
        self.assertEqual(low_stock.data["count"], 1)
        self.assertEqual(low_stock.data["results"][0]["available"], 0)

    def test_threshold_list_requires_inventory_permission(self):
        self.client.force_authenticate(self.user)
        response = self.client.get("/api/inventory/thresholds/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["minimum_quantity"], 0)

    def test_summary_reports_threshold_management_permission(self):
        self.client.force_authenticate(self.user)
        viewer_summary = self.client.get("/api/inventory/summary/")
        self.assertEqual(viewer_summary.status_code, 200)
        self.assertFalse(viewer_summary.data["can_manage_threshold"])

        self.client.force_authenticate(self.manager)
        manager_summary = self.client.get("/api/inventory/summary/")
        self.assertEqual(manager_summary.status_code, 200)
        self.assertTrue(manager_summary.data["can_manage_threshold"])

    def test_summary_reports_document_workflow_permissions(self):
        creator_permission = Permission.objects.get(codename="can_create_inventory_document")
        reviewer_permission = Permission.objects.get(codename="can_review_inventory_document")
        self.user.user_permissions.add(creator_permission, reviewer_permission)

        self.client.force_authenticate(self.user)
        creator_summary = self.client.get("/api/inventory/summary/")
        self.assertEqual(creator_summary.status_code, 200)
        self.assertTrue(creator_summary.data["can_create_document"])
        self.assertTrue(creator_summary.data["can_review_document"])
        self.assertFalse(creator_summary.data["can_approve_document"])

        self.client.force_authenticate(self.manager)
        manager_summary = self.client.get("/api/inventory/summary/")
        self.assertTrue(manager_summary.data["can_approve_document"])

    def test_draft_item_can_only_be_removed_by_creator_with_permission(self):
        creator_permission = Permission.objects.get(codename="can_create_inventory_document")
        self.user.user_permissions.add(creator_permission)
        self.client.force_authenticate(self.user)
        response = self.client.delete(
            f"/api/inventory/documents/{self.document.id}/items/{self.item.id}/"
        )
        self.assertEqual(response.status_code, 204)
        self.assertFalse(InventoryDocumentItem.objects.filter(pk=self.item.id).exists())

    def test_draft_item_removal_is_denied_to_non_creator(self):
        creator_permission = Permission.objects.get(codename="can_create_inventory_document")
        self.manager.user_permissions.add(creator_permission)
        self.client.force_authenticate(self.manager)
        response = self.client.delete(
            f"/api/inventory/documents/{self.document.id}/items/{self.item.id}/"
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(InventoryDocumentItem.objects.filter(pk=self.item.id).exists())

    def test_document_operational_workflow_creates_stock_only_after_manager_approval(self):
        creator_permission = Permission.objects.get(codename="can_create_inventory_document")
        reviewer_permission = Permission.objects.get(codename="can_review_inventory_document")
        approver_permission = Permission.objects.get(codename="can_approve_inventory_document")
        self.user.user_permissions.add(creator_permission)
        accountant = User.objects.create_user(username="dashboard_accountant", password="test-pass")
        accountant.user_permissions.add(reviewer_permission)
        self.manager.user_permissions.add(approver_permission)

        self.client.force_authenticate(self.user)
        created = self.client.post(
            "/api/inventory/documents/create/",
            {
                "document_number": "DASH-WORKFLOW-001",
                "document_type": "purchase",
                "reason": "Purchase receipt",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        document_id = created.data["id"]

        added = self.client.post(
            f"/api/inventory/documents/{document_id}/items/",
            {
                "variant": self.variant.id,
                "quantity": 7,
                "direction": "inbound",
                "new_batch_number": "DASH-WORKFLOW-BATCH",
                "unit_cost": "125000",
            },
            format="json",
        )
        self.assertEqual(added.status_code, 201)

        submitted = self.client.post(
            f"/api/inventory/documents/{document_id}/submit/",
            {},
            format="json",
        )
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.data["status"], "pending_review")

        self.client.force_authenticate(accountant)
        reviewed = self.client.post(
            f"/api/inventory/documents/{document_id}/review/",
            {"note": "Invoice checked"},
            format="json",
        )
        self.assertEqual(reviewed.status_code, 200)
        self.assertEqual(reviewed.data["status"], "pending_approval")

        self.client.force_authenticate(self.manager)
        approved = self.client.post(
            f"/api/inventory/documents/{document_id}/approve/",
            {"note": "Approved"},
            format="json",
        )
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.data["status"], "approved")
        self.assertEqual(
            InventoryDocument.objects.get(pk=document_id).items.first().movements.count(),
            1,
        )
        self.assertEqual(
            InventoryDocumentLog.objects.filter(document_id=document_id).count(),
            5,
        )
