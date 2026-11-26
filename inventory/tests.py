from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import close_old_connections
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.db import connection
from django.test.utils import CaptureQueriesContext
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
    InventoryDocumentLog,
)
from .services import (
    allocate_stock_reservation,
    get_batch_physical_quantity,
    get_batch_reserved_quantity,
    get_batch_available_quantity,
    get_variant_inventory,
    get_variants_inventory,
)
from .sale_services import record_order_sale


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

    def create_order_item(self, reservation):
        from orders.models import OrderItem

        return OrderItem.objects.create(
            order=reservation.order,
            variant=reservation.variant,
            product_name=self.product.name_fa,
            product_slug=self.product.slug,
            brand_name=self.brand.name,
            variant_label="Test Variant",
            price=100000,
            quantity=reservation.quantity,
            subtotal=100000 * reservation.quantity,
        )

    def test_unbatched_stock_can_be_reserved_and_sold(self):
        unbatched = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="",
            created_by=self.user,
        )
        self.create_movement(unbatched, 8)

        inventory = get_variant_inventory(
            self.variant,
            today=self.today,
            now=self.now,
        )
        self.assertEqual(inventory["physical"], 8)
        self.assertEqual(inventory["available"], 8)

        reservation = self.create_reservation(quantity=3)
        allocate_stock_reservation(reservation, now=self.now)

        allocation = ReservationAllocation.objects.get(reservation=reservation)
        self.assertEqual(allocation.batch_id, unbatched.id)
        self.assertEqual(allocation.quantity, 3)

        self.create_order_item(reservation)
        document = record_order_sale(
            reservation.order,
            reservations=[reservation],
            now=self.now,
        )

        sale_movement = InventoryMovement.objects.get(document=document)
        self.assertEqual(sale_movement.batch_id, unbatched.id)
        self.assertEqual(sale_movement.quantity_delta, -3)
        self.assertEqual(get_batch_physical_quantity(unbatched), 5)

    def test_multiple_unbatched_lots_are_allowed_but_named_batches_stay_unique(self):
        first = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="",
            created_by=self.user,
        )
        second = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="",
            created_by=self.user,
        )
        self.assertNotEqual(first.id, second.id)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryBatch.objects.create(
                    variant=self.variant,
                    batch_number="BATCH-001",
                    created_by=self.user,
                )

    def test_get_variants_inventory_returns_grouped_ledger_inventory(self):
        self.create_movement(self.batch, 10)

        reservation = self.create_reservation(
            quantity=3,
            batch=self.batch,
        )

        second_variant = ProductVariant.objects.create(
            product=self.product,
            flavor="Second Variant",
            price=120000,
            stock=999,
        )

        second_batch = InventoryBatch.objects.create(
            variant=second_variant,
            batch_number="GROUP-TEST-002",
            created_by=self.user,
        )
        self.create_movement(second_batch, 4)

        inventory = get_variants_inventory(
            [self.variant, second_variant],
            today=self.today,
            now=self.now,
        )

        self.assertEqual(
            inventory[self.variant.id],
            {
                "physical": 10,
                "reserved": 3,
                "available": 7,
            },
        )
        self.assertEqual(
            inventory[second_variant.id],
            {
                "physical": 4,
                "reserved": 0,
                "available": 4,
            },
        )

    def test_get_variants_inventory_excludes_unavailable_batches(self):
        self.create_movement(self.batch, 10)

        quarantined_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="GROUP-QUARANTINED",
            created_by=self.user,
            status="quarantined",
        )
        self.create_movement(quarantined_batch, 5)

        blocked_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="GROUP-BLOCKED",
            created_by=self.user,
            status="blocked",
        )
        self.create_movement(blocked_batch, 7)

        expired_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="GROUP-EXPIRED",
            created_by=self.user,
            expiration_date=self.today - timedelta(days=1),
        )
        self.create_movement(expired_batch, 8)

        inventory = get_variants_inventory(
            [self.variant],
            today=self.today,
            now=self.now,
        )

        self.assertEqual(
            inventory[self.variant.id],
            {
                "physical": 30,
                "reserved": 0,
                "available": 10,
            },
        )

    def test_get_variants_inventory_ignores_expired_reservations(self):
        self.create_movement(self.batch, 20)

        self.create_reservation(
            quantity=5,
            batch=self.batch,
            expires_at=self.now - timedelta(minutes=1),
        )

        inventory = get_variants_inventory(
            [self.variant],
            today=self.today,
            now=self.now,
        )

        self.assertEqual(
            inventory[self.variant.id],
            {
                "physical": 20,
                "reserved": 0,
                "available": 20,
            },
        )

    def test_get_variants_inventory_returns_empty_dict_for_empty_input(self):
        self.assertEqual(
            get_variants_inventory(
                [],
                today=self.today,
                now=self.now,
            ),
            {},
        )

    def test_get_variants_inventory_query_count_is_constant(self):
        additional_variants = [
            ProductVariant.objects.create(
                product=self.product,
                flavor=f"Variant {index}",
                price=100000 + index,
                stock=0,
            )
            for index in range(5)
        ]

        one_variant = [self.variant]
        six_variants = [self.variant, *additional_variants]

        with CaptureQueriesContext(connection) as single_queries:
            get_variants_inventory(
                one_variant,
                today=self.today,
                now=self.now,
            )

        with CaptureQueriesContext(connection) as multiple_queries:
            get_variants_inventory(
                six_variants,
                today=self.today,
                now=self.now,
            )

        self.assertEqual(len(single_queries), 3)
        self.assertEqual(len(multiple_queries), 3)

    def test_record_order_sale_creates_outbound_document_and_consumes_reservation(self):
        self.create_movement(self.batch, 10)

        reservation = self.create_reservation(
            quantity=3,
            batch=self.batch,
        )
        self.create_order_item(reservation)

        document = record_order_sale(
            reservation.order,
            now=self.now,
        )

        reservation.refresh_from_db()
        self.batch.refresh_from_db()

        movement = InventoryMovement.objects.get(
            document=document,
        )

        self.assertEqual(document.document_type, "outbound")
        self.assertEqual(document.status, "approved")
        self.assertEqual(document.source_order_id, reservation.order_id)
        self.assertEqual(movement.quantity_delta, -3)
        self.assertEqual(movement.batch_id, self.batch.id)
        self.assertEqual(get_batch_physical_quantity(self.batch), 7)
        self.assertEqual(reservation.status, "consumed")
        self.assertEqual(reservation.consumed_at, self.now)

    def test_record_order_sale_is_idempotent(self):
        self.create_movement(self.batch, 10)

        reservation = self.create_reservation(
            quantity=3,
            batch=self.batch,
        )
        self.create_order_item(reservation)

        first_document = record_order_sale(
            reservation.order,
            now=self.now,
        )
        second_document = record_order_sale(
            reservation.order,
            now=self.now,
        )

        self.assertEqual(first_document.pk, second_document.pk)
        self.assertEqual(
            InventoryDocument.objects.filter(
                source_order=reservation.order,
            ).count(),
            1,
        )
        self.assertEqual(
            InventoryMovement.objects.filter(
                document=first_document,
            ).count(),
            1,
        )
        self.assertEqual(get_batch_physical_quantity(self.batch), 7)

    def test_record_order_sale_rejects_incomplete_allocation(self):
        from django.core.exceptions import ValidationError

        self.create_movement(self.batch, 10)

        reservation = self.create_reservation(quantity=3)
        self.create_order_item(reservation)

        with self.assertRaises(ValidationError):
            record_order_sale(
                reservation.order,
                now=self.now,
            )

        reservation.refresh_from_db()

        self.assertEqual(reservation.status, "active")
        self.assertEqual(get_batch_physical_quantity(self.batch), 10)
        self.assertFalse(
            InventoryDocument.objects.filter(
                source_order=reservation.order,
            ).exists()
        )

    def test_record_order_sale_rejects_insufficient_physical_stock(self):
        from django.core.exceptions import ValidationError

        self.create_movement(self.batch, 2)

        reservation = self.create_reservation(
            quantity=3,
            batch=self.batch,
        )
        self.create_order_item(reservation)

        with self.assertRaises(ValidationError):
            record_order_sale(
                reservation.order,
                now=self.now,
            )

        reservation.refresh_from_db()

        self.assertEqual(reservation.status, "active")
        self.assertEqual(get_batch_physical_quantity(self.batch), 2)
        self.assertFalse(
            InventoryDocument.objects.filter(
                source_order=reservation.order,
            ).exists()
        )

    def test_record_order_sale_rejects_unavailable_batch(self):
        from django.core.exceptions import ValidationError

        self.create_movement(self.batch, 10)

        reservation = self.create_reservation(
            quantity=3,
            batch=self.batch,
        )
        self.create_order_item(reservation)

        self.batch.status = "quarantined"
        self.batch.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            record_order_sale(
                reservation.order,
                now=self.now,
            )

        reservation.refresh_from_db()

        self.assertEqual(reservation.status, "active")
        self.assertEqual(get_batch_physical_quantity(self.batch), 10)
        self.assertFalse(
            InventoryDocument.objects.filter(
                source_order=reservation.order,
            ).exists()
        )

    def test_record_order_sale_rejects_expired_batch(self):
        from django.core.exceptions import ValidationError

        self.create_movement(self.batch, 10)

        reservation = self.create_reservation(
            quantity=3,
            batch=self.batch,
        )
        self.create_order_item(reservation)

        self.batch.expiration_date = self.today - timedelta(days=1)
        self.batch.save(update_fields=["expiration_date"])

        with self.assertRaises(ValidationError):
            record_order_sale(
                reservation.order,
                now=self.now,
            )

        reservation.refresh_from_db()

        self.assertEqual(reservation.status, "active")
        self.assertEqual(get_batch_physical_quantity(self.batch), 10)
        self.assertFalse(
            InventoryDocument.objects.filter(
                source_order=reservation.order,
            ).exists()
        )

    def test_record_order_sale_uses_exact_multi_batch_allocations(self):
        self.create_movement(self.batch, 10)

        second_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="BATCH-002",
            expiration_date=self.today + timedelta(days=60),
            created_by=self.user,
        )
        self.create_movement(second_batch, 10)

        reservation = self.create_reservation(quantity=5)
        ReservationAllocation.objects.create(
            reservation=reservation,
            batch=self.batch,
            quantity=2,
        )
        ReservationAllocation.objects.create(
            reservation=reservation,
            batch=second_batch,
            quantity=3,
        )
        self.create_order_item(reservation)

        document = record_order_sale(
            reservation.order,
            now=self.now,
        )

        movements = InventoryMovement.objects.filter(
            document=document,
        ).order_by("batch_id")

        self.assertEqual(movements.count(), 2)
        self.assertEqual(
            list(movements.values_list("batch_id", "quantity_delta")),
            [
                (self.batch.id, -2),
                (second_batch.id, -3),
            ],
        )
        self.assertEqual(get_batch_physical_quantity(self.batch), 8)
        self.assertEqual(get_batch_physical_quantity(second_batch), 7)

        reservation.refresh_from_db()
        self.assertEqual(reservation.status, "consumed")

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

    def test_batch_available_quantity_protects_unallocated_reservations_by_fefo(self):
        self.create_movement(self.batch, 10)
        second_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="BATCH-UNALLOCATED-002",
            expiration_date=self.today + timedelta(days=60),
            created_by=self.user,
        )
        self.create_movement(second_batch, 10)
        self.create_reservation(quantity=6)

        self.assertEqual(
            get_batch_available_quantity(
                self.batch,
                today=self.today,
                now=self.now,
            ),
            4,
        )
        self.assertEqual(
            get_batch_available_quantity(
                second_batch,
                today=self.today,
                now=self.now,
            ),
            10,
        )

    def test_batch_inventory_combines_explicit_and_unallocated_reservations(self):
        self.create_movement(self.batch, 10)
        second_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="BATCH-MIXED-002",
            expiration_date=self.today + timedelta(days=60),
            created_by=self.user,
        )
        self.create_movement(second_batch, 10)

        reservation = self.create_reservation(quantity=5)
        ReservationAllocation.objects.create(
            reservation=reservation,
            batch=second_batch,
            quantity=2,
        )

        self.assertEqual(
            get_batch_available_quantity(
                self.batch,
                today=self.today,
                now=self.now,
            ),
            7,
        )
        self.assertEqual(
            get_batch_available_quantity(
                second_batch,
                today=self.today,
                now=self.now,
            ),
            8,
        )

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

    def test_allocate_reservation_uses_fefo_order(self):
        second_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="BATCH-002",
            expiration_date=self.today + timedelta(days=60),
            created_by=self.user,
        )

        self.create_movement(self.batch, 3)
        self.create_movement(second_batch, 5)

        reservation = self.create_reservation(quantity=6)

        allocate_stock_reservation(reservation, now=self.now)

        allocations = list(
            ReservationAllocation.objects.filter(
                reservation=reservation,
            )
            .order_by(
                "batch__expiration_date",
            )
            .values_list(
                "batch__batch_number",
                "quantity",
            )
        )

        self.assertEqual(
            allocations,
            [
                ("BATCH-001", 3),
                ("BATCH-002", 3),
            ],
        )

    def test_allocate_reservation_protects_unallocated_reservations(self):
        self.create_movement(self.batch, 10)

        existing_reservation = self.create_reservation(
            quantity=7,
        )

        new_reservation = self.create_reservation(
            quantity=3,
        )

        allocate_stock_reservation(
            new_reservation,
            now=self.now,
        )

        allocations = ReservationAllocation.objects.filter(
            reservation=new_reservation,
        )

        self.assertEqual(
            allocations.aggregate(total=Sum("quantity"))["total"],
            3,
        )

        self.assertFalse(
            ReservationAllocation.objects.filter(
                reservation=existing_reservation,
            ).exists()
        )

    def test_allocate_reservation_rolls_back_when_stock_is_insufficient(self):
        from django.core.exceptions import ValidationError

        self.create_movement(self.batch, 5)

        reservation = self.create_reservation(quantity=6)

        with self.assertRaises(ValidationError):
            allocate_stock_reservation(
                reservation,
                now=self.now,
            )

        self.assertFalse(
            ReservationAllocation.objects.filter(
                reservation=reservation,
            ).exists()
        )

    def test_allocate_reservation_ignores_unavailable_batches(self):
        quarantined_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="BATCH-QUARANTINED",
            status="quarantined",
            created_by=self.user,
        )

        blocked_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="BATCH-BLOCKED",
            status="blocked",
            created_by=self.user,
        )

        expired_batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="BATCH-EXPIRED",
            expiration_date=self.today - timedelta(days=1),
            created_by=self.user,
        )

        for batch in (
            quarantined_batch,
            blocked_batch,
            expired_batch,
        ):
            self.create_movement(batch, 5)

        reservation = self.create_reservation(quantity=1)

        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            allocate_stock_reservation(
                reservation,
                now=self.now,
            )

        self.assertFalse(
            ReservationAllocation.objects.filter(
                reservation=reservation,
            ).exists()
        )

    def test_allocate_reservation_rejects_duplicate_allocation(self):
        self.create_movement(self.batch, 5)

        reservation = self.create_reservation(
            quantity=2,
            batch=self.batch,
        )

        from django.core.exceptions import ValidationError

        with self.assertRaises(ValidationError):
            allocate_stock_reservation(
                reservation,
                now=self.now,
            )

        self.assertEqual(
            ReservationAllocation.objects.filter(
                reservation=reservation,
            ).count(),
            1,
        )

    def test_allocate_reservation_rejects_inactive_reservation(self):
        from django.core.exceptions import ValidationError

        self.create_movement(self.batch, 5)

        reservation = self.create_reservation(quantity=2)
        reservation.status = "expired"
        reservation.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            allocate_stock_reservation(
                reservation,
                now=self.now,
            )

        self.assertFalse(
            ReservationAllocation.objects.filter(
                reservation=reservation,
            ).exists()
        )

    def test_allocate_reservation_rejects_expired_reservation(self):
        from django.core.exceptions import ValidationError

        self.create_movement(self.batch, 5)

        reservation = self.create_reservation(
            quantity=2,
            expires_at=self.now - timedelta(seconds=1),
        )

        with self.assertRaises(ValidationError):
            allocate_stock_reservation(
                reservation,
                now=self.now,
            )

        self.assertFalse(
            ReservationAllocation.objects.filter(
                reservation=reservation,
            ).exists()
        )

    def test_allocate_reservation_rejects_expired_order(self):
        from django.core.exceptions import ValidationError

        self.create_movement(self.batch, 5)

        reservation = self.create_reservation(quantity=2)

        reservation.order.reservation_expires_at = self.now - timedelta(seconds=1)
        reservation.order.save(update_fields=["reservation_expires_at"])

        with self.assertRaises(ValidationError):
            allocate_stock_reservation(
                reservation,
                now=self.now,
            )

        self.assertFalse(
            ReservationAllocation.objects.filter(
                reservation=reservation,
            ).exists()
        )

    def test_allocate_reservation_rejects_non_pending_order(self):
        from django.core.exceptions import ValidationError

        self.create_movement(self.batch, 5)

        reservation = self.create_reservation(quantity=2)
        reservation.order.status = "cancelled"
        reservation.order.save(update_fields=["status"])

        with self.assertRaises(ValidationError):
            allocate_stock_reservation(
                reservation,
                now=self.now,
            )

        self.assertFalse(
            ReservationAllocation.objects.filter(
                reservation=reservation,
            ).exists()
        )


    def test_allocate_reservation_rechecks_order_after_loading_stale_reservation(self):
        from django.core.exceptions import ValidationError

        self.create_movement(self.batch, 5)
        reservation = self.create_reservation(quantity=2)

        # Simulate a worker holding a reservation object loaded before another
        # transaction cancels its order and releases the reservation.
        stale_reservation = StockReservation.objects.select_related(
            "order",
        ).get(pk=reservation.pk)

        Order.objects.filter(pk=reservation.order_id).update(
            status="cancelled",
        )
        StockReservation.objects.filter(pk=reservation.pk).update(
            status="released",
            released_at=self.now,
        )

        with self.assertRaises(ValidationError):
            allocate_stock_reservation(
                stale_reservation,
                now=self.now,
            )

        self.assertFalse(
            ReservationAllocation.objects.filter(
                reservation=reservation,
            ).exists()
        )
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, "released")


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

    def test_database_rejects_negative_unit_cost(self):
        from django.db import IntegrityError, transaction

        document = InventoryDocument.objects.create(
            document_number="NEGATIVE-COST-DB-001",
            document_type="inbound",
            created_by=self.creator,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryDocumentItem.objects.create(
                    document=document,
                    variant=self.variant,
                    quantity=1,
                    direction="inbound",
                    new_batch_number="NEGATIVE-COST-DB-BATCH",
                    unit_cost=-100,
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

    def test_outbound_document_cannot_consume_reserved_stock(self):
        from django.core.exceptions import ValidationError
        from orders.models import Order, StockReservation
        from .services import get_variant_inventory

        now = timezone.now()
        today = timezone.localdate()
        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="RESERVED-BOUNDARY-001",
            expiration_date=today + timedelta(days=30),
            created_by=self.creator,
        )

        inbound = create_inventory_document(
            user=self.creator,
            document_number="RESERVED-BOUNDARY-IN",
            document_type="inbound",
        )
        add_inventory_document_item(
            user=self.creator,
            document_id=inbound.id,
            variant=self.variant,
            quantity=10,
            direction="inbound",
            batch=batch,
        )
        submit_inventory_document(user=self.creator, document_id=inbound.id)
        review_inventory_document(user=self.reviewer, document_id=inbound.id)
        approve_inventory_document(user=self.approver, document_id=inbound.id)

        order = Order.objects.create(
            user=self.creator,
            first_name="Reserved",
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

        outbound = create_inventory_document(
            user=self.creator,
            document_number="RESERVED-BOUNDARY-OUT",
            document_type="outbound",
        )
        add_inventory_document_item(
            user=self.creator,
            document_id=outbound.id,
            variant=self.variant,
            quantity=7,
            direction="outbound",
        )
        submit_inventory_document(user=self.creator, document_id=outbound.id)
        review_inventory_document(user=self.reviewer, document_id=outbound.id)

        with self.assertRaises(ValidationError):
            approve_inventory_document(
                user=self.approver,
                document_id=outbound.id,
            )

        outbound.refresh_from_db()
        self.assertEqual(outbound.status, "pending_approval")
        self.assertFalse(
            InventoryMovement.objects.filter(document=outbound).exists()
        )
        inventory = get_variant_inventory(self.variant, now=now)
        self.assertEqual(inventory["physical"], 10)
        self.assertEqual(inventory["reserved"], 4)
        self.assertEqual(inventory["available"], 6)

    def test_batch_specific_outbound_rejects_unallocated_variant_reservations(self):
        from django.core.exceptions import ValidationError
        from orders.models import Order, StockReservation

        now = timezone.now()
        today = timezone.localdate()
        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="RESERVED-BATCH-SPECIFIC-001",
            expiration_date=today + timedelta(days=30),
            created_by=self.creator,
        )

        inbound = create_inventory_document(
            user=self.creator,
            document_number="RESERVED-BATCH-SPECIFIC-IN",
            document_type="inbound",
        )
        add_inventory_document_item(
            user=self.creator,
            document_id=inbound.id,
            variant=self.variant,
            quantity=10,
            direction="inbound",
            batch=batch,
        )
        submit_inventory_document(user=self.creator, document_id=inbound.id)
        review_inventory_document(user=self.reviewer, document_id=inbound.id)
        approve_inventory_document(user=self.approver, document_id=inbound.id)

        order = Order.objects.create(
            user=self.creator,
            first_name="Reserved",
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
            quantity=2,
            status="active",
            expires_at=now + timedelta(minutes=10),
        )

        outbound = create_inventory_document(
            user=self.creator,
            document_number="RESERVED-BATCH-SPECIFIC-OUT",
            document_type="outbound",
        )
        add_inventory_document_item(
            user=self.creator,
            document_id=outbound.id,
            variant=self.variant,
            quantity=2,
            direction="outbound",
            batch=batch,
        )
        submit_inventory_document(user=self.creator, document_id=outbound.id)
        review_inventory_document(user=self.reviewer, document_id=outbound.id)

        with self.assertRaises(ValidationError):
            approve_inventory_document(
                user=self.approver,
                document_id=outbound.id,
            )

        outbound.refresh_from_db()
        self.assertEqual(outbound.status, "pending_approval")
        self.assertFalse(
            InventoryMovement.objects.filter(document=outbound).exists()
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

    def test_inbound_document_accepts_optional_batch_and_expiration(self):
        document = create_inventory_document(
            user=self.creator,
            document_number="INBOUND-NO-BATCH-001",
            document_type="inbound",
        )

        add_inventory_document_item(
            user=self.creator,
            document_id=document.id,
            variant=self.variant,
            quantity=4,
            direction="inbound",
        )
        add_inventory_document_item(
            user=self.creator,
            document_id=document.id,
            variant=self.variant,
            quantity=2,
            direction="inbound",
            new_batch_expiration_date=timezone.localdate() + timedelta(days=45),
        )

        submit_inventory_document(user=self.creator, document_id=document.id)
        review_inventory_document(user=self.reviewer, document_id=document.id)
        approve_inventory_document(user=self.approver, document_id=document.id)

        movements = list(
            InventoryMovement.objects.filter(document=document).select_related("batch")
        )
        self.assertEqual(len(movements), 2)
        self.assertEqual({movement.batch.batch_number for movement in movements}, {""})
        self.assertEqual(
            {movement.batch.expiration_date for movement in movements},
            {None, timezone.localdate() + timedelta(days=45)},
        )
        self.assertTrue(
            all(movement.batch.status == "available" for movement in movements)
        )
        self.assertEqual(sum(movement.quantity_delta for movement in movements), 6)

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
        self.assertEqual(movement.batch.batch_number, "")
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

    def test_inventory_movement_system_creator_can_be_null(self):
        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="SYSTEM-MOVEMENT-BATCH-001",
            created_by=self.creator,
        )

        document = create_inventory_document(
            user=self.creator,
            document_number="SYSTEM-MOVEMENT-DOC-001",
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
            created_by_type="system",
            created_by=None,
        )

        self.assertEqual(movement.created_by_type, "system")
        self.assertIsNone(movement.created_by_id)

    def test_inventory_movement_rejects_system_creator_with_user(self):
        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="SYSTEM-MOVEMENT-BATCH-INVALID-001",
            created_by=self.creator,
        )

        document = create_inventory_document(
            user=self.creator,
            document_number="SYSTEM-MOVEMENT-DOC-INVALID-001",
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

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryMovement.objects.bulk_create(
                    [
                        InventoryMovement(
                            batch=batch,
                            document=document,
                            document_item=item,
                            movement_type="inbound",
                            quantity_delta=5,
                            created_by_type="system",
                            created_by=self.creator,
                        )
                    ]
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

    def test_inventory_document_system_creator_can_be_null(self):
        document = InventoryDocument.objects.create(
            document_number="SYSTEM-DOC-001",
            document_type="outbound",
            created_by_type="system",
            created_by=None,
            source_order_id=None,
        )

        self.assertEqual(document.created_by_type, "system")
        self.assertIsNone(document.created_by_id)

    def test_inventory_document_rejects_system_creator_with_user(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryDocument.objects.create(
                    document_number="SYSTEM-DOC-INVALID-001",
                    document_type="outbound",
                    created_by_type="system",
                    created_by=self.creator,
                )

    def test_inventory_document_log_system_actor_can_be_null(self):
        document = InventoryDocument.objects.create(
            document_number="SYSTEM-LOG-DOC-001",
            document_type="outbound",
            created_by=self.creator,
        )

        log = InventoryDocumentLog.objects.create(
            document=document,
            action="created",
            actor_type="system",
            actor=None,
        )

        self.assertEqual(log.actor_type, "system")
        self.assertIsNone(log.actor_id)

    def test_inventory_document_log_rejects_system_actor_with_user(self):
        document = InventoryDocument.objects.create(
            document_number="SYSTEM-LOG-INVALID-001",
            document_type="outbound",
            created_by=self.creator,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                InventoryDocumentLog.objects.create(
                    document=document,
                    action="created",
                    actor_type="system",
                    actor=self.creator,
                )

    def test_system_approval_allows_valid_inventory_sale_document(self):
        order = Order.objects.create(
            user=self.creator,
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
        )

        document = InventoryDocument.objects.create(
            document_number="SYSTEM-APPROVAL-001",
            document_type="outbound",
            source_order=order,
            created_by_type="system",
            created_by=None,
        )

        from django.utils import timezone

        document.status = "approved"
        document.approved_at = timezone.now()
        document.save(
            update_fields=["status", "approved_at", "updated_at"],
            _allow_system_approval=True,
        )

        document.refresh_from_db()
        self.assertEqual(document.status, "approved")
        self.assertIsNotNone(document.approved_at)

    def test_system_approval_rejects_user_created_document(self):
        from django.utils import timezone
        from django.core.exceptions import ValidationError

        now = timezone.now()

        order = Order.objects.create(
            user=self.creator,
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
        )

        document = InventoryDocument.objects.create(
            document_number="USER-SALE-001",
            document_type="outbound",
            source_order=order,
            created_by_type="user",
            created_by=self.creator,
        )

        document.status = "approved"
        document.approved_at = now

        with self.assertRaises(ValidationError):
            document.save(
                update_fields=["status", "approved_at", "updated_at"],
                _allow_system_approval=True,
            )

    def test_system_approval_rejects_update_without_status(self):
        from django.core.exceptions import ValidationError

        order = Order.objects.create(
            user=self.creator,
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
        )

        document = InventoryDocument.objects.create(
            document_number="SYSTEM-APPROVAL-002",
            document_type="outbound",
            source_order=order,
            created_by_type="system",
            created_by=None,
        )

        with self.assertRaises(ValidationError):
            document.save(
                update_fields=["updated_at"],
                _allow_system_approval=True,
            )


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

    def test_document_history_uses_official_role_title(self):
        from django.contrib.auth.models import Group
        from .dashboard_serializers import _person_info

        internal_manager, _ = Group.objects.get_or_create(name="مدیر داخلی")
        self.user.first_name = "مینا"
        self.user.last_name = "نوشانی"
        self.user.save(update_fields=["first_name", "last_name"])
        self.user.groups.add(internal_manager)

        approve_permission = Permission.objects.get(
            content_type__app_label="inventory",
            codename="can_approve_inventory_document",
        )
        self.user.user_permissions.add(approve_permission)

        self.assertEqual(
            _person_info(self.user),
            ("مینا نوشانی", "مدیر داخلی"),
        )

    def test_executive_history_keeps_executive_title_despite_broad_permissions(self):
        from django.contrib.auth.models import Group
        from .dashboard_serializers import _person_info

        ceo, _ = Group.objects.get_or_create(name="مدیرعامل")
        self.user.groups.add(ceo)
        self.user.user_permissions.add(self.permission)

        self.assertEqual(
            _person_info(self.user),
            ("inventory_report_user", "مدیرعامل"),
        )

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

    def test_creator_without_report_permission_cannot_read_global_stock_panels(self):
        create_permission = Permission.objects.get(
            content_type__app_label="inventory",
            codename="can_create_inventory_document",
        )
        self.user.user_permissions.add(create_permission)
        self.client.force_authenticate(user=self.user)

        summary = self.client.get("/api/inventory/summary/")
        self.assertEqual(summary.status_code, 200)
        self.assertFalse(summary.data["can_view_reports"])
        self.assertFalse(summary.data["can_manage_threshold"])
        self.assertEqual(summary.data["sku_count"], 0)
        self.assertEqual(summary.data["physical_quantity"], 0)

        self.assertEqual(self.client.get("/api/inventory/low-stock/").status_code, 403)
        self.assertEqual(self.client.get("/api/inventory/thresholds/").status_code, 403)

    def test_threshold_management_requires_dedicated_permission(self):
        threshold_permission = Permission.objects.get(
            content_type__app_label="inventory",
            codename="can_manage_inventory_thresholds",
        )
        self.client.force_authenticate(user=self.user)

        self.assertEqual(self.client.get("/api/inventory/thresholds/").status_code, 403)
        self.assertEqual(
            self.client.put(
                f"/api/inventory/thresholds/{self.variant.id}/",
                {"minimum_quantity": 7},
                format="json",
            ).status_code,
            403,
        )

        self.user.user_permissions.add(threshold_permission)
        self.assertEqual(self.client.get("/api/inventory/thresholds/").status_code, 200)
        response = self.client.put(
            f"/api/inventory/thresholds/{self.variant.id}/",
            {"minimum_quantity": 7},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["minimum_quantity"], 7)


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

    def test_complete_unbatched_inbound_document_workflow(self):
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
        response = self.client.get("/api/inventory/documents/")
        self.assertEqual(response.status_code, 200)
        listed_document = next(
            item for item in response.data["results"]
            if item["id"] == document_id
        )
        self.assertEqual(listed_document["item_count"], 1)

        self.client.force_authenticate(user=self.reviewer)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/review/",
            {"note": "Reviewed through API"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "pending_approval")

        response = self.client.get("/api/inventory/documents/")
        self.assertEqual(response.status_code, 200)
        listed_document = next(
            item for item in response.data["results"]
            if item["id"] == document_id
        )
        self.assertEqual(listed_document["item_count"], 1)

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
            batch_number="",
        )

        movement = InventoryMovement.objects.get(document=document)

        self.assertEqual(movement.batch, batch)
        self.assertEqual(movement.quantity_delta, 5)
        self.assertEqual(movement.movement_type, "inbound")

    def test_document_item_rejects_negative_unit_cost(self):
        self.client.force_authenticate(user=self.creator)

        response = self.client.post(
            "/api/inventory/documents/",
            {
                "document_number": "API-NEGATIVE-COST-001",
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
                "quantity": 1,
                "direction": "inbound",
                "new_batch_number": "API-NEGATIVE-COST-BATCH",
                "unit_cost": -100,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)

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
        approve_permission = Permission.objects.get(
            content_type__app_label="inventory",
            codename="can_approve_inventory_document",
        )
        self.creator.user_permissions.add(approve_permission)

        self.client.force_authenticate(user=self.reviewer)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/review/",
            {"note": "Reviewed"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        self.client.force_authenticate(user=self.creator)

        response = self.client.post(
            f"/api/inventory/documents/{document_id}/reject/",
            {"note": "Self rejection at approval stage"},
            format="json",
        )

        self.assertEqual(response.status_code, 403)

        document.refresh_from_db()
        self.assertEqual(document.status, "pending_approval")

    def test_document_actions_return_404_for_missing_document(self):
        self.client.raise_request_exception = False

        cases = [
            (
                self.creator,
                "/api/inventory/documents/999999/items/",
                {
                    "variant": self.variant.id,
                    "quantity": 1,
                    "direction": "inbound",
                    "new_batch_number": "MISSING-DOC-BATCH",
                },
            ),
            (
                self.creator,
                "/api/inventory/documents/999999/submit/",
                {},
            ),
            (
                self.reviewer,
                "/api/inventory/documents/999999/review/",
                {"note": "Review"},
            ),
            (
                self.reviewer,
                "/api/inventory/documents/999999/reject/",
                {"note": "Rejection reason"},
            ),
            (
                self.approver,
                "/api/inventory/documents/999999/approve/",
                {"note": "Approval"},
            ),
        ]

        for user, url, data in cases:
            with self.subTest(url=url):
                self.client.force_authenticate(user=user)

                response = self.client.post(
                    url,
                    data,
                    format="json",
                )

                self.assertEqual(response.status_code, 404)


class InventoryConcurrentApprovalTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        InventoryDocumentWorkflowTests.setUp(self)

        today = timezone.localdate()
        self.batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="CONCURRENT-APPROVAL-SEED",
            expiration_date=today + timedelta(days=30),
            created_by=self.creator,
        )
        inbound = create_inventory_document(
            user=self.creator,
            document_number="CONCURRENT-APPROVAL-IN",
            document_type="inbound",
        )
        add_inventory_document_item(
            user=self.creator,
            document_id=inbound.id,
            variant=self.variant,
            quantity=10,
            direction="inbound",
            batch=self.batch,
        )
        submit_inventory_document(user=self.creator, document_id=inbound.id)
        review_inventory_document(user=self.reviewer, document_id=inbound.id)
        approve_inventory_document(user=self.approver, document_id=inbound.id)

        self.outbound_documents = []
        for suffix in ("A", "B"):
            document = create_inventory_document(
                user=self.creator,
                document_number=f"CONCURRENT-APPROVAL-OUT-{suffix}",
                document_type="outbound",
            )
            add_inventory_document_item(
                user=self.creator,
                document_id=document.id,
                variant=self.variant,
                quantity=6,
                direction="outbound",
            )
            submit_inventory_document(
                user=self.creator,
                document_id=document.id,
            )
            review_inventory_document(
                user=self.reviewer,
                document_id=document.id,
            )
            self.outbound_documents.append(document)

    @skipUnlessDBFeature("has_select_for_update")
    def test_concurrent_outbound_approvals_cannot_oversell_same_sku(self):
        from django.core.exceptions import ValidationError

        barrier = Barrier(2)

        def approve(document_id):
            close_old_connections()
            try:
                approver = User.objects.get(pk=self.approver.pk)
                barrier.wait(timeout=10)
                try:
                    approve_inventory_document(
                        user=approver,
                        document_id=document_id,
                    )
                    return "approved"
                except ValidationError:
                    return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(approve, document.id)
                for document in self.outbound_documents
            ]
            outcomes = [future.result(timeout=30) for future in futures]

        self.assertCountEqual(outcomes, ["approved", "rejected"])

        for document in self.outbound_documents:
            document.refresh_from_db()

        self.assertEqual(
            sum(doc.status == "approved" for doc in self.outbound_documents),
            1,
        )
        self.assertEqual(
            sum(
                InventoryMovement.objects.filter(
                    document=doc,
                    movement_type="outbound",
                ).aggregate(total=Sum("quantity_delta"))["total"] or 0
                for doc in self.outbound_documents
            ),
            -6,
        )
        inventory = get_variant_inventory(self.variant)
        self.assertEqual(inventory["physical"], 4)
        self.assertEqual(inventory["reserved"], 0)
        self.assertEqual(inventory["available"], 4)
