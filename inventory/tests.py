from datetime import timedelta
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from django.utils import timezone
from catalog.models import Brand, Category, Product, ProductVariant
from orders.models import Order, StockReservation
from .models import (
    InventoryBatch,
    InventoryDocument,
    InventoryMovement,
    ReservationAllocation,
    InventoryDocumentItem,
    InventoryStockThreshold,
)
from .services import (
    get_batch_physical_quantity,
    get_batch_reserved_quantity,
    get_batch_available_quantity,
    get_variant_inventory,
)


class InventoryServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="inventory_test_user",
            password="test-password",
        )

        self.brand = Brand.objects.create(
            name="Test Brand",
            slug="test-brand",
        )

        self.category = Category.objects.create(
            name="Test Category",
            slug="test-category",
        )

        self.product = Product.objects.create(
            name_fa="Test Product",
            slug="test-product",
            brand=self.brand,
            category=self.category,
            description="Test description",
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=100000,
            stock=0,
        )

        self.today = timezone.localdate()
        self.now = timezone.now()

        self.batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="BATCH-001",
            expiration_date=self.today + timedelta(days=30),
            created_by=self.user,
        )

    def create_movement(self, batch, quantity_delta):
        document = self.create_document(quantity_delta)
        item = self.create_document_item(document, batch, quantity_delta)

        return InventoryMovement.objects.create(
            batch=batch,
            document=document,
            document_item=item,
            movement_type=("inbound" if quantity_delta > 0 else "outbound"),
            quantity_delta=quantity_delta,
            created_by=self.user,
        )

    def create_document(self, quantity_delta):
        from .models import InventoryDocument

        return InventoryDocument.objects.create(
            document_number=f"DOC-{InventoryDocument.objects.count() + 1:04d}",
            document_type=("inbound" if quantity_delta > 0 else "outbound"),
            created_by=self.user,
        )

    def create_document_item(self, document, batch, quantity_delta):
        from .models import InventoryDocumentItem

        return InventoryDocumentItem.objects.create(
            document=document,
            variant=batch.variant,
            batch=batch,
            quantity=abs(quantity_delta),
            direction=("inbound" if quantity_delta > 0 else "outbound"),
        )

    def create_reservation(self, quantity, batch=None, expires_at=None):
        order = Order.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            mobile="09120000000",
            province="tehran",
            city="Tehran",
            address="Test address",
            subtotal=100000,
            vat_amount=0,
            total_amount=100000,
            status="pending",
            reservation_expires_at=self.now + timedelta(minutes=10),
        )

        reservation = StockReservation.objects.create(
            order=order,
            variant=self.variant,
            quantity=quantity,
            status="active",
            expires_at=expires_at or self.now + timedelta(minutes=5),
        )

        if batch:
            ReservationAllocation.objects.create(
                reservation=reservation,
                batch=batch,
                quantity=quantity,
            )

        return reservation

    def test_physical_quantity_is_sum_of_movements(self):
        self.create_movement(self.batch, 20)
        self.create_movement(self.batch, -3)

        self.assertEqual(
            get_batch_physical_quantity(self.batch),
            17,
        )

    def test_active_reservation_is_subtracted(self):
        self.create_movement(self.batch, 20)
        self.create_reservation(5, batch=self.batch)

        self.assertEqual(
            get_batch_reserved_quantity(self.batch, now=self.now),
            5,
        )

        self.assertEqual(
            get_batch_available_quantity(
                self.batch,
                today=self.today,
                now=self.now,
            ),
            15,
        )

    def test_unallocated_reservation_is_subtracted_from_variant_inventory(self):
        self.create_movement(self.batch, 20)
        self.create_reservation(5)

        inventory = get_variant_inventory(
            self.variant,
            today=self.today,
            now=self.now,
        )

        self.assertEqual(inventory["physical"], 20)
        self.assertEqual(inventory["reserved"], 5)
        self.assertEqual(inventory["available"], 15)

    def test_expired_reservation_is_not_counted(self):
        self.create_movement(self.batch, 20)
        self.create_reservation(
            5,
            batch=self.batch,
            expires_at=self.now - timedelta(minutes=1),
        )

        self.assertEqual(
            get_batch_reserved_quantity(self.batch, now=self.now),
            0,
        )

    def test_expired_batch_is_not_sellable(self):
        self.create_movement(self.batch, 20)

        self.batch.expiration_date = self.today - timedelta(days=1)
        self.batch.save(update_fields=["expiration_date"])

        self.assertEqual(
            get_batch_available_quantity(
                self.batch,
                today=self.today,
                now=self.now,
            ),
            0,
        )

    def test_quarantined_batch_is_not_sellable(self):
        self.create_movement(self.batch, 20)

        self.batch.status = "quarantined"
        self.batch.save(update_fields=["status"])

        self.assertEqual(
            get_batch_available_quantity(
                self.batch,
                today=self.today,
                now=self.now,
            ),
            0,
        )

    def test_blocked_batch_is_not_sellable(self):
        self.create_movement(self.batch, 20)

        self.batch.status = "blocked"
        self.batch.save(update_fields=["status"])

        self.assertEqual(
            get_batch_available_quantity(
                self.batch,
                today=self.today,
                now=self.now,
            ),
            0,
        )

    def test_variant_inventory_sums_multiple_batches(self):
        self.create_movement(self.batch, 20)

        second_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="BATCH-002",
            expiration_date=self.today + timedelta(days=60),
            created_by=self.user,
        )

        self.create_movement(second_batch, 10)
        self.create_reservation(5, batch=self.batch)

        result = get_variant_inventory(
            self.variant,
            today=self.today,
            now=self.now,
        )

        self.assertEqual(result["physical"], 30)
        self.assertEqual(result["reserved"], 5)
        self.assertEqual(result["available"], 25)


from .document_services import (
    create_inventory_document,
    add_inventory_document_item,
    submit_inventory_document,
    review_inventory_document,
    approve_inventory_document,
)


class InventoryDocumentWorkflowTests(TestCase):
    def setUp(self):
        self.creator = User.objects.create_user(
            username="inventory_creator",
            password="test-password",
        )
        self.reviewer = User.objects.create_user(
            username="inventory_reviewer",
            password="test-password",
        )
        self.approver = User.objects.create_user(
            username="inventory_approver",
            password="test-password",
        )

        permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="inventory",
                codename__in=[
                    "can_create_inventory_document",
                    "can_review_inventory_document",
                    "can_approve_inventory_document",
                ],
            )
        }

        self.creator.user_permissions.add(
            permissions["can_create_inventory_document"],
        )
        self.reviewer.user_permissions.add(
            permissions["can_review_inventory_document"],
        )
        self.approver.user_permissions.add(
            permissions["can_approve_inventory_document"],
        )

        brand = Brand.objects.create(
            name="Workflow Brand",
            slug="workflow-brand",
        )
        category = Category.objects.create(
            name="Workflow Category",
            slug="workflow-category",
        )
        product = Product.objects.create(
            name_fa="Workflow Product",
            slug="workflow-product",
            brand=brand,
            category=category,
            description="Workflow test product",
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            price=100000,
            stock=0,
        )

    def test_submit_rejects_invalid_document_type(self):
        from django.core.exceptions import ValidationError
        from .models import InventoryDocument

        document = InventoryDocument.objects.create(
            document_number="INVALID-TYPE-001",
            document_type="invalid",
            created_by=self.creator,
        )

        InventoryDocumentItem.objects.create(
            document=document,
            variant=self.variant,
            quantity=5,
            direction="inbound",
            new_batch_number="INVALID-TYPE-BATCH-001",
        )

        with self.assertRaises(ValidationError):
            submit_inventory_document(
                user=self.creator,
                document_id=document.id,
            )

        document.refresh_from_db()
        self.assertEqual(document.status, "draft")

    def test_approve_rejects_invalid_document_type(self):
        from django.core.exceptions import ValidationError
        from .models import InventoryDocument

        document = InventoryDocument.objects.create(
            document_number="INVALID-APPROVAL-001",
            document_type="invalid",
            created_by=self.creator,
        )

        InventoryDocumentItem.objects.create(
            document=document,
            variant=self.variant,
            quantity=5,
            direction="inbound",
            new_batch_number="INVALID-APPROVAL-BATCH-001",
        )

        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE inventory_inventorydocument SET status = %s WHERE id = %s",
                ["pending_approval", document.pk],
            )

        with self.assertRaises(ValidationError):
            approve_inventory_document(
                user=self.approver,
                document_id=document.id,
            )

        document.refresh_from_db()
        self.assertEqual(document.status, "pending_approval")
        self.assertFalse(InventoryMovement.objects.filter(document=document).exists())

    def test_add_item_rejects_invalid_document_type(self):
        from django.core.exceptions import ValidationError
        from .models import InventoryDocument

        document = InventoryDocument.objects.create(
            document_number="INVALID-ITEM-001",
            document_type="invalid",
            created_by=self.creator,
        )

        with self.assertRaises(ValidationError):
            add_inventory_document_item(
                user=self.creator,
                document_id=document.id,
                variant=self.variant,
                quantity=5,
                direction="inbound",
                new_batch_number="INVALID-ITEM-BATCH-001",
            )

        self.assertFalse(
            InventoryDocumentItem.objects.filter(document=document).exists()
        )

    def test_existing_batch_rejects_new_batch_expiration_date(self):
        from django.core.exceptions import ValidationError

        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="VALIDATION-BATCH-001",
            expiration_date=timezone.localdate() + timedelta(days=30),
            created_by=self.creator,
        )

        document = create_inventory_document(
            user=self.creator,
            document_number="VALIDATION-DOC-001",
            document_type="inbound",
        )

        with self.assertRaises(ValidationError):
            add_inventory_document_item(
                user=self.creator,
                document_id=document.id,
                variant=self.variant,
                quantity=5,
                direction="inbound",
                batch=batch,
                new_batch_expiration_date=(timezone.localdate() + timedelta(days=60)),
            )

    def test_past_batch_expiration_date_is_rejected(self):
        from django.core.exceptions import ValidationError

        document = create_inventory_document(
            user=self.creator,
            document_number="VALIDATION-DOC-002",
            document_type="inbound",
        )

        with self.assertRaises(ValidationError):
            add_inventory_document_item(
                user=self.creator,
                document_id=document.id,
                variant=self.variant,
                quantity=5,
                direction="inbound",
                new_batch_number="VALIDATION-BATCH-002",
                new_batch_expiration_date=(timezone.localdate() - timedelta(days=1)),
            )

        self.assertFalse(
            InventoryDocumentItem.objects.filter(
                document=document,
            ).exists()
        )

    def test_submit_rejects_direct_item_with_past_expiration_date(self):
        from django.core.exceptions import ValidationError

        document = create_inventory_document(
            user=self.creator,
            document_number="VALIDATION-DOC-003",
            document_type="inbound",
        )

        InventoryDocumentItem.objects.create(
            document=document,
            variant=self.variant,
            quantity=5,
            direction="inbound",
            new_batch_number="VALIDATION-BATCH-003",
            new_batch_expiration_date=(timezone.localdate() - timedelta(days=1)),
        )

        with self.assertRaises(ValidationError):
            submit_inventory_document(
                user=self.creator,
                document_id=document.id,
            )

        document.refresh_from_db()
        self.assertEqual(document.status, "draft")

    def test_inbound_document_workflow_creates_stock_movement(self):
        document = create_inventory_document(
            user=self.creator,
            document_number="WORKFLOW-IN-001",
            document_type="inbound",
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=document.id,
            variant=self.variant,
            quantity=20,
            direction="inbound",
            new_batch_number="WORKFLOW-BATCH-001",
            new_batch_expiration_date=(timezone.localdate() + timedelta(days=60)),
        )

        submit_inventory_document(
            user=self.creator,
            document_id=document.id,
        )

        review_inventory_document(
            user=self.reviewer,
            document_id=document.id,
            note="Initial review",
        )

        approved_document = approve_inventory_document(
            user=self.approver,
            document_id=document.id,
            note="Final approval",
        )

        self.assertEqual(approved_document.status, "approved")
        self.assertEqual(approved_document.approved_by, self.approver)

        movement = InventoryMovement.objects.get(
            document=approved_document,
        )

        self.assertEqual(movement.quantity_delta, 20)
        self.assertEqual(movement.movement_type, "inbound")
        self.assertEqual(movement.batch.variant, self.variant)
        self.assertEqual(movement.batch.status, "available")
        self.assertEqual(
            movement.batch.batch_number,
            "WORKFLOW-BATCH-001",
        )

    def test_reviewer_cannot_approve_same_document(self):
        document = create_inventory_document(
            user=self.creator,
            document_number="WORKFLOW-IN-002",
            document_type="inbound",
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=document.id,
            variant=self.variant,
            quantity=10,
            direction="inbound",
            new_batch_number="WORKFLOW-BATCH-002",
        )

        submit_inventory_document(
            user=self.creator,
            document_id=document.id,
        )

        review_inventory_document(
            user=self.reviewer,
            document_id=document.id,
        )

        from django.core.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            approve_inventory_document(
                user=self.reviewer,
                document_id=document.id,
            )

        document.refresh_from_db()

        self.assertEqual(document.status, "pending_approval")
        self.assertFalse(
            InventoryMovement.objects.filter(
                document=document,
            ).exists()
        )

    def test_outbound_document_uses_fefo_batches(self):
        from .models import InventoryBatch

        today = timezone.localdate()

        first_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="FEFO-001",
            expiration_date=today + timedelta(days=10),
            created_by=self.creator,
        )

        second_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="FEFO-002",
            expiration_date=today + timedelta(days=30),
            created_by=self.creator,
        )

        inbound_document = create_inventory_document(
            user=self.creator,
            document_number="FEFO-IN-001",
            document_type="inbound",
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=inbound_document.id,
            variant=self.variant,
            quantity=10,
            direction="inbound",
            batch=first_batch,
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=inbound_document.id,
            variant=self.variant,
            quantity=10,
            direction="inbound",
            batch=second_batch,
        )

        submit_inventory_document(
            user=self.creator,
            document_id=inbound_document.id,
        )
        review_inventory_document(
            user=self.reviewer,
            document_id=inbound_document.id,
        )
        approve_inventory_document(
            user=self.approver,
            document_id=inbound_document.id,
        )

        outbound_document = create_inventory_document(
            user=self.creator,
            document_number="FEFO-OUT-001",
            document_type="outbound",
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=outbound_document.id,
            variant=self.variant,
            quantity=12,
            direction="outbound",
        )

        submit_inventory_document(
            user=self.creator,
            document_id=outbound_document.id,
        )
        review_inventory_document(
            user=self.reviewer,
            document_id=outbound_document.id,
        )
        approve_inventory_document(
            user=self.approver,
            document_id=outbound_document.id,
        )

        movements = list(
            InventoryMovement.objects.filter(
                document=outbound_document,
            ).order_by("batch__expiration_date")
        )

        self.assertEqual(len(movements), 2)
        self.assertEqual(movements[0].batch, first_batch)
        self.assertEqual(movements[0].quantity_delta, -10)
        self.assertEqual(movements[1].batch, second_batch)
        self.assertEqual(movements[1].quantity_delta, -2)

    def test_outbound_document_preserves_reserved_stock(self):
        from orders.models import Order, StockReservation

        today = timezone.localdate()
        now = timezone.now()

        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="RESERVED-001",
            expiration_date=today + timedelta(days=30),
            created_by=self.creator,
        )

        inbound_document = create_inventory_document(
            user=self.creator,
            document_number="RESERVED-IN-001",
            document_type="inbound",
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=inbound_document.id,
            variant=self.variant,
            quantity=10,
            direction="inbound",
            batch=batch,
        )

        submit_inventory_document(
            user=self.creator,
            document_id=inbound_document.id,
        )
        review_inventory_document(
            user=self.reviewer,
            document_id=inbound_document.id,
        )
        approve_inventory_document(
            user=self.approver,
            document_id=inbound_document.id,
        )

        order = Order.objects.create(
            user=self.creator,
            first_name="Test",
            last_name="Customer",
            mobile="09120000000",
            province="tehran",
            city="Tehran",
            address="Test address",
            subtotal=100000,
            vat_amount=0,
            total_amount=100000,
            status="pending",
            reservation_expires_at=now + timedelta(minutes=20),
        )

        StockReservation.objects.create(
            order=order,
            variant=self.variant,
            quantity=4,
            status="active",
            expires_at=now + timedelta(minutes=10),
        )

        outbound_document = create_inventory_document(
            user=self.creator,
            document_number="RESERVED-OUT-001",
            document_type="outbound",
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=outbound_document.id,
            variant=self.variant,
            quantity=6,
            direction="outbound",
        )

        submit_inventory_document(
            user=self.creator,
            document_id=outbound_document.id,
        )
        review_inventory_document(
            user=self.reviewer,
            document_id=outbound_document.id,
        )
        approve_inventory_document(
            user=self.approver,
            document_id=outbound_document.id,
        )

        movement = InventoryMovement.objects.get(
            document=outbound_document,
        )

        self.assertEqual(movement.quantity_delta, -6)

        from .services import get_batch_physical_quantity

        self.assertEqual(
            get_batch_physical_quantity(batch),
            4,
        )

    def test_insufficient_stock_rolls_back_all_movements(self):
        from django.core.exceptions import ValidationError

        inbound_document = create_inventory_document(
            user=self.creator,
            document_number="ROLLBACK-IN-001",
            document_type="inbound",
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=inbound_document.id,
            variant=self.variant,
            quantity=10,
            direction="inbound",
            new_batch_number="ROLLBACK-BATCH-001",
        )

        submit_inventory_document(
            user=self.creator,
            document_id=inbound_document.id,
        )
        review_inventory_document(
            user=self.reviewer,
            document_id=inbound_document.id,
        )
        approve_inventory_document(
            user=self.approver,
            document_id=inbound_document.id,
        )

        outbound_document = create_inventory_document(
            user=self.creator,
            document_number="ROLLBACK-OUT-001",
            document_type="outbound",
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=outbound_document.id,
            variant=self.variant,
            quantity=11,
            direction="outbound",
        )

        submit_inventory_document(
            user=self.creator,
            document_id=outbound_document.id,
        )
        review_inventory_document(
            user=self.reviewer,
            document_id=outbound_document.id,
        )

        with self.assertRaises(ValidationError):
            approve_inventory_document(
                user=self.approver,
                document_id=outbound_document.id,
            )

        outbound_document.refresh_from_db()

        self.assertEqual(outbound_document.status, "pending_approval")
        self.assertFalse(
            InventoryMovement.objects.filter(
                document=outbound_document,
            ).exists()
        )

    def test_return_document_creates_quarantined_batch(self):
        return_document = create_inventory_document(
            user=self.creator,
            document_number="RETURN-001",
            document_type="return",
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=return_document.id,
            variant=self.variant,
            quantity=3,
            direction="inbound",
            new_batch_number="RETURN-BATCH-001",
        )

        submit_inventory_document(
            user=self.creator,
            document_id=return_document.id,
        )
        review_inventory_document(
            user=self.reviewer,
            document_id=return_document.id,
        )
        approve_inventory_document(
            user=self.approver,
            document_id=return_document.id,
        )

        movement = InventoryMovement.objects.get(
            document=return_document,
        )

        self.assertEqual(movement.movement_type, "return")
        self.assertEqual(movement.quantity_delta, 3)
        self.assertEqual(movement.batch.status, "quarantined")

        from .services import get_batch_available_quantity

        self.assertEqual(
            get_batch_available_quantity(movement.batch),
            0,
        )

    def test_adjustment_document_supports_positive_and_negative_movements(self):
        positive_document = create_inventory_document(
            user=self.creator,
            document_number="ADJUSTMENT-POS-001",
            document_type="adjustment",
            reason="Positive stock correction",
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=positive_document.id,
            variant=self.variant,
            quantity=10,
            direction="inbound",
            new_batch_number="ADJUSTMENT-BATCH-001",
            reason="Positive stock correction",
        )

        submit_inventory_document(
            user=self.creator,
            document_id=positive_document.id,
        )
        review_inventory_document(
            user=self.reviewer,
            document_id=positive_document.id,
        )
        approve_inventory_document(
            user=self.approver,
            document_id=positive_document.id,
        )

        positive_movement = InventoryMovement.objects.get(
            document=positive_document,
        )

        self.assertEqual(positive_movement.movement_type, "adjustment")
        self.assertEqual(positive_movement.quantity_delta, 10)

        negative_document = create_inventory_document(
            user=self.creator,
            document_number="ADJUSTMENT-NEG-001",
            document_type="adjustment",
            reason="Negative stock correction",
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=negative_document.id,
            variant=self.variant,
            quantity=3,
            direction="outbound",
            reason="Negative stock correction",
        )

        submit_inventory_document(
            user=self.creator,
            document_id=negative_document.id,
        )
        review_inventory_document(
            user=self.reviewer,
            document_id=negative_document.id,
        )
        approve_inventory_document(
            user=self.approver,
            document_id=negative_document.id,
        )

        negative_movement = InventoryMovement.objects.get(
            document=negative_document,
        )

        self.assertEqual(negative_movement.movement_type, "adjustment")
        self.assertEqual(negative_movement.quantity_delta, -3)

    def test_movement_rejects_item_from_another_document(self):
        from django.core.exceptions import ValidationError

        document = create_inventory_document(
            user=self.creator,
            document_number="MOVEMENT-DOC-001",
            document_type="inbound",
        )
        another_document = create_inventory_document(
            user=self.creator,
            document_number="MOVEMENT-DOC-002",
            document_type="inbound",
        )

        item = add_inventory_document_item(
            user=self.creator,
            document_id=document.id,
            variant=self.variant,
            quantity=5,
            direction="inbound",
            new_batch_number="MOVEMENT-BATCH-001",
        )

        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="MOVEMENT-BATCH-002",
            created_by=self.creator,
        )

        with self.assertRaises(ValidationError):
            InventoryMovement.objects.create(
                batch=batch,
                document=another_document,
                document_item=item,
                movement_type="inbound",
                quantity_delta=5,
                created_by=self.creator,
            )

    def test_movement_rejects_batch_from_another_variant(self):
        from django.core.exceptions import ValidationError

        other_variant = ProductVariant.objects.create(
            product=self.variant.product,
            flavor="Different flavor",
            price=200000,
            stock=0,
        )

        document = create_inventory_document(
            user=self.creator,
            document_number="MOVEMENT-VARIANT-001",
            document_type="inbound",
        )

        item = add_inventory_document_item(
            user=self.creator,
            document_id=document.id,
            variant=self.variant,
            quantity=5,
            direction="inbound",
            new_batch_number="MOVEMENT-VARIANT-BATCH-001",
        )

        batch = InventoryBatch.objects.create(
            variant=other_variant,
            batch_number="MOVEMENT-VARIANT-BATCH-002",
            created_by=self.creator,
        )

        with self.assertRaises(ValidationError):
            InventoryMovement.objects.create(
                batch=batch,
                document=document,
                document_item=item,
                movement_type="inbound",
                quantity_delta=5,
                created_by=self.creator,
            )

    def test_movement_rejects_inconsistent_quantity_sign(self):
        from django.core.exceptions import ValidationError

        document = create_inventory_document(
            user=self.creator,
            document_number="MOVEMENT-SIGN-001",
            document_type="inbound",
        )

        item = add_inventory_document_item(
            user=self.creator,
            document_id=document.id,
            variant=self.variant,
            quantity=5,
            direction="inbound",
            new_batch_number="MOVEMENT-SIGN-BATCH-001",
        )

        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="MOVEMENT-SIGN-BATCH-002",
            created_by=self.creator,
        )

        with self.assertRaises(ValidationError):
            InventoryMovement.objects.create(
                batch=batch,
                document=document,
                document_item=item,
                movement_type="inbound",
                quantity_delta=-5,
                created_by=self.creator,
            )

    def test_movement_rejects_inconsistent_movement_type(self):
        from django.core.exceptions import ValidationError

        document = create_inventory_document(
            user=self.creator,
            document_number="MOVEMENT-TYPE-001",
            document_type="inbound",
        )

        item = add_inventory_document_item(
            user=self.creator,
            document_id=document.id,
            variant=self.variant,
            quantity=5,
            direction="inbound",
            new_batch_number="MOVEMENT-TYPE-BATCH-001",
        )

        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="MOVEMENT-TYPE-BATCH-002",
            created_by=self.creator,
        )

        with self.assertRaises(ValidationError):
            InventoryMovement.objects.create(
                batch=batch,
                document=document,
                document_item=item,
                movement_type="outbound",
                quantity_delta=5,
                created_by=self.creator,
            )

    def test_inventory_movement_cannot_be_updated(self):
        from django.core.exceptions import ValidationError

        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="IMMUTABLE-001",
            created_by=self.creator,
        )

        document = create_inventory_document(
            user=self.creator,
            document_number="IMMUTABLE-DOC-001",
            document_type="inbound",
        )

        item = add_inventory_document_item(
            user=self.creator,
            document_id=document.id,
            variant=self.variant,
            quantity=5,
            direction="inbound",
            batch=batch,
        )

        movement = InventoryMovement.objects.create(
            batch=batch,
            document=document,
            document_item=item,
            movement_type="inbound",
            quantity_delta=5,
            created_by=self.creator,
        )

        movement.quantity_delta = 10

        with self.assertRaises(ValidationError):
            movement.save()

        movement.refresh_from_db()
        self.assertEqual(movement.quantity_delta, 5)

    def test_inventory_movement_cannot_be_deleted(self):
        from django.core.exceptions import ValidationError

        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="IMMUTABLE-002",
            created_by=self.creator,
        )

        document = create_inventory_document(
            user=self.creator,
            document_number="IMMUTABLE-DOC-002",
            document_type="inbound",
        )

        item = add_inventory_document_item(
            user=self.creator,
            document_id=document.id,
            variant=self.variant,
            quantity=5,
            direction="inbound",
            batch=batch,
        )

        movement = InventoryMovement.objects.create(
            batch=batch,
            document=document,
            document_item=item,
            movement_type="inbound",
            quantity_delta=5,
            created_by=self.creator,
        )

        with self.assertRaises(ValidationError):
            movement.delete()

        self.assertTrue(InventoryMovement.objects.filter(pk=movement.pk).exists())

    def test_inventory_movement_queryset_modifications_are_blocked(self):
        from django.core.exceptions import ValidationError

        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="QUERYSET-IMMUTABLE-001",
            created_by=self.creator,
        )

        document = create_inventory_document(
            user=self.creator,
            document_number="QUERYSET-IMMUTABLE-DOC-001",
            document_type="inbound",
        )

        item = add_inventory_document_item(
            user=self.creator,
            document_id=document.id,
            variant=self.variant,
            quantity=5,
            direction="inbound",
            batch=batch,
        )

        movement = InventoryMovement.objects.create(
            batch=batch,
            document=document,
            document_item=item,
            movement_type="inbound",
            quantity_delta=5,
            created_by=self.creator,
        )

        queryset = InventoryMovement.objects.filter(pk=movement.pk)

        with self.assertRaises(ValidationError):
            queryset.update(quantity_delta=10)

        with self.assertRaises(ValidationError):
            queryset.delete()

        movement.quantity_delta = 10

        with self.assertRaises(ValidationError):
            InventoryMovement.objects.bulk_update(
                [movement],
                ["quantity_delta"],
            )

        movement.refresh_from_db()
        self.assertEqual(movement.quantity_delta, 5)
        self.assertTrue(InventoryMovement.objects.filter(pk=movement.pk).exists())

    def test_inventory_document_log_is_immutable(self):
        from django.core.exceptions import ValidationError
        from .models import InventoryDocumentLog

        document = create_inventory_document(
            user=self.creator,
            document_number="IMMUTABLE-LOG-DOC-001",
            document_type="inbound",
        )

        log = InventoryDocumentLog.objects.filter(
            document=document,
        ).first()

        self.assertIsNotNone(log)

        log.note = "Modified note"

        with self.assertRaises(ValidationError):
            log.save()

        with self.assertRaises(ValidationError):
            log.delete()

        queryset = InventoryDocumentLog.objects.filter(
            pk=log.pk,
        )

        with self.assertRaises(ValidationError):
            queryset.update(note="Modified note")

        with self.assertRaises(ValidationError):
            queryset.delete()

        with self.assertRaises(ValidationError):
            InventoryDocumentLog.objects.bulk_update(
                [log],
                ["note"],
            )

        log.refresh_from_db()
        self.assertNotEqual(log.note, "Modified note")

    def test_document_items_are_immutable_after_submission(self):
        from django.core.exceptions import ValidationError

        document = create_inventory_document(
            user=self.creator,
            document_number="IMMUTABLE-ITEM-DOC-001",
            document_type="inbound",
        )

        item = add_inventory_document_item(
            user=self.creator,
            document_id=document.id,
            variant=self.variant,
            quantity=5,
            direction="inbound",
            new_batch_number="IMMUTABLE-ITEM-BATCH-001",
        )

        submit_inventory_document(
            user=self.creator,
            document_id=document.id,
        )

        item.reason = "Modified reason"

        with self.assertRaises(ValidationError):
            item.save()

        with self.assertRaises(ValidationError):
            item.delete()

        queryset = InventoryDocumentItem.objects.filter(
            pk=item.pk,
        )

        with self.assertRaises(ValidationError):
            queryset.update(quantity=10)

        with self.assertRaises(ValidationError):
            queryset.delete()

        with self.assertRaises(ValidationError):
            InventoryDocumentItem.objects.bulk_update(
                [item],
                ["quantity"],
            )

        item.refresh_from_db()
        self.assertEqual(item.quantity, 5)

    def test_inventory_document_cannot_be_modified_directly(self):
        from django.core.exceptions import ValidationError

        document = create_inventory_document(
            user=self.creator,
            document_number="IMMUTABLE-DOC-001",
            document_type="inbound",
        )

        document.notes = "Unauthorized modification"

        with self.assertRaises(ValidationError):
            document.save()

        with self.assertRaises(ValidationError):
            document.delete()

        queryset = type(document).objects.filter(pk=document.pk)

        with self.assertRaises(ValidationError):
            queryset.update(status="approved")

        with self.assertRaises(ValidationError):
            queryset.delete()

        with self.assertRaises(ValidationError):
            type(document).objects.bulk_update(
                [document],
                ["notes"],
            )

        document.refresh_from_db()
        self.assertEqual(document.status, "draft")
        self.assertEqual(document.notes, "")


class InventoryReportAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.user = User.objects.create_user(
            username="inventory_report_user",
            password="test-password",
        )

        self.brand = Brand.objects.create(
            name="Report Brand",
            slug="report-brand",
        )

        self.category = Category.objects.create(
            name="Report Category",
            slug="report-category",
        )

        self.product = Product.objects.create(
            name_fa="Report Product",
            slug="report-product",
            brand=self.brand,
            category=self.category,
            description="Report test product",
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=100000,
            stock=0,
        )

        self.permission = Permission.objects.get(
            content_type__app_label="inventory",
            codename="can_view_inventory_reports",
        )

    def test_user_without_permission_cannot_view_report(self):
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/inventory/reports/")

        self.assertEqual(response.status_code, 403)

    def test_user_with_permission_can_view_report(self):
        self.user.user_permissions.add(self.permission)
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/inventory/reports/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

        report = response.data[0]

        self.assertEqual(report["sku"], self.variant.sku)
        self.assertEqual(report["physical"], 0)
        self.assertEqual(report["reserved"], 0)
        self.assertEqual(report["available"], 0)
        self.assertEqual(report["minimum_quantity"], 0)
        self.assertFalse(report["low_stock"])
        self.assertNotIn("batch", report)
        self.assertNotIn("expiration_date", report)

    def test_report_marks_low_stock_variant(self):
        self.user.user_permissions.add(self.permission)
        self.client.force_authenticate(user=self.user)

        InventoryStockThreshold.objects.create(
            variant=self.variant,
            minimum_quantity=5,
            updated_by=self.user,
        )

        response = self.client.get("/api/inventory/reports/")

        self.assertEqual(response.status_code, 200)

        report = response.data[0]

        self.assertEqual(report["minimum_quantity"], 5)
        self.assertTrue(report["low_stock"])


class InventoryDocumentAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.creator = User.objects.create_user(
            username="api_doc_creator",
            password="test-password",
        )
        self.reviewer = User.objects.create_user(
            username="api_doc_reviewer",
            password="test-password",
        )
        self.approver = User.objects.create_user(
            username="api_doc_approver",
            password="test-password",
        )

        permissions = {
            permission.codename: permission
            for permission in Permission.objects.filter(
                content_type__app_label="inventory",
                codename__in=[
                    "can_create_inventory_document",
                    "can_review_inventory_document",
                    "can_approve_inventory_document",
                ],
            )
        }

        self.creator.user_permissions.add(
            permissions["can_create_inventory_document"],
        )
        self.reviewer.user_permissions.add(
            permissions["can_review_inventory_document"],
        )
        self.approver.user_permissions.add(
            permissions["can_approve_inventory_document"],
        )

        brand = Brand.objects.create(
            name="API Brand",
            slug="api-brand",
        )
        category = Category.objects.create(
            name="API Category",
            slug="api-category",
        )
        product = Product.objects.create(
            name_fa="API Product",
            slug="api-product",
            brand=brand,
            category=category,
            description="API test product",
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            price=100000,
            stock=0,
        )

    def test_user_without_permission_cannot_create_document(self):
        user = User.objects.create_user(
            username="api_doc_unauthorized",
            password="test-password",
        )
        self.client.force_authenticate(user=user)

        response = self.client.post(
            "/api/inventory/documents/",
            {
                "document_number": "API-UNAUTHORIZED-001",
                "document_type": "inbound",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)

    def test_complete_inbound_document_workflow(self):
        self.client.force_authenticate(user=self.creator)

        response = self.client.post(
            "/api/inventory/documents/",
            {
                "document_number": "API-WORKFLOW-001",
                "document_type": "inbound",
                "reason": "API workflow test",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        document_id = response.data["id"]
        self.assertEqual(response.data["status"], "draft")

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/items/",
            {
                "variant": self.variant.id,
                "quantity": 5,
                "direction": "inbound",
                "new_batch_number": "API-BATCH-001",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/submit/",
            {},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "pending_review")

        self.client.force_authenticate(user=self.reviewer)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/review/",
            {"note": "Reviewed through API"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "pending_approval")

        self.client.force_authenticate(user=self.approver)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/approve/",
            {"note": "Approved through API"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "approved")

        document = InventoryDocument.objects.get(pk=document_id)

        self.assertEqual(document.created_by, self.creator)
        self.assertEqual(document.reviewed_by, self.reviewer)
        self.assertEqual(document.approved_by, self.approver)

        batch = InventoryBatch.objects.get(
            variant=self.variant,
            batch_number="API-BATCH-001",
        )

        movement = InventoryMovement.objects.get(document=document)

        self.assertEqual(movement.batch, batch)
        self.assertEqual(movement.quantity_delta, 5)
        self.assertEqual(movement.movement_type, "inbound")

    def test_reviewer_can_reject_document_through_api(self):
        self.client.force_authenticate(user=self.creator)

        response = self.client.post(
            "/api/inventory/documents/",
            {
                "document_number": "API-REJECT-001",
                "document_type": "inbound",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        document_id = response.data["id"]

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/items/",
            {
                "variant": self.variant.id,
                "quantity": 3,
                "direction": "inbound",
                "new_batch_number": "API-REJECT-BATCH-001",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/submit/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        self.client.force_authenticate(user=self.reviewer)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/reject/",
            {"note": "Invalid document"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "rejected")

        document = InventoryDocument.objects.get(pk=document_id)
        self.assertEqual(document.status, "rejected")

    def test_reviewer_cannot_approve_document(self):
        self.client.force_authenticate(user=self.creator)

        response = self.client.post(
            "/api/inventory/documents/",
            {
                "document_number": "API-REVIEWER-APPROVE-001",
                "document_type": "inbound",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        document_id = response.data["id"]

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/items/",
            {
                "variant": self.variant.id,
                "quantity": 3,
                "direction": "inbound",
                "new_batch_number": "API-REVIEWER-APPROVE-BATCH-001",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/submit/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        self.client.force_authenticate(user=self.reviewer)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/approve/",
            {"note": "Direct approval attempt"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

        document = InventoryDocument.objects.get(pk=document_id)
        self.assertEqual(document.status, "pending_review")

    def test_creator_cannot_review_own_document(self):
        self.client.force_authenticate(user=self.creator)

        response = self.client.post(
            "/api/inventory/documents/",
            {
                "document_number": "API-CREATOR-REVIEW-001",
                "document_type": "inbound",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        document_id = response.data["id"]

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/items/",
            {
                "variant": self.variant.id,
                "quantity": 3,
                "direction": "inbound",
                "new_batch_number": "API-CREATOR-REVIEW-BATCH-001",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/submit/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/review/",
            {"note": "Self review attempt"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

        document = InventoryDocument.objects.get(pk=document_id)
        self.assertEqual(document.status, "pending_review")

    def test_creator_cannot_approve_own_document(self):
        approve_permission = Permission.objects.get(
            content_type__app_label="inventory",
            codename="can_approve_inventory_document",
        )
        self.creator.user_permissions.add(approve_permission)

        self.client.force_authenticate(user=self.creator)

        response = self.client.post(
            "/api/inventory/documents/",
            {
                "document_number": "API-CREATOR-APPROVE-001",
                "document_type": "inbound",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        document_id = response.data["id"]

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/items/",
            {
                "variant": self.variant.id,
                "quantity": 3,
                "direction": "inbound",
                "new_batch_number": "API-CREATOR-APPROVE-BATCH-001",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/submit/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        self.client.force_authenticate(user=self.reviewer)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/review/",
            {"note": "Reviewed"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        self.client.force_authenticate(user=self.creator)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/approve/",
            {"note": "Self approval attempt"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

        document = InventoryDocument.objects.get(pk=document_id)
        self.assertEqual(document.status, "pending_approval")

    def test_creator_cannot_reject_own_document(self):
        self.client.force_authenticate(user=self.creator)

        response = self.client.post(
            "/api/inventory/documents/",
            {
                "document_number": "API-CREATOR-REJECT-001",
                "document_type": "inbound",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        document_id = response.data["id"]

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/items/",
            {
                "variant": self.variant.id,
                "quantity": 3,
                "direction": "inbound",
                "new_batch_number": "API-CREATOR-REJECT-BATCH-001",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/submit/",
            {},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/reject/",
            {"note": "Self rejection attempt"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

        document = InventoryDocument.objects.get(pk=document_id)
        self.assertEqual(document.status, "pending_review")
