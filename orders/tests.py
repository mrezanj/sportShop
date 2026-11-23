from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch
from orders.admin import OrderAdmin
from django.contrib.auth.models import User, Permission
from users.models import Profile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase
from inventory.models import (
    InventoryBatch,
    InventoryDocument,
    InventoryDocumentItem,
    InventoryMovement,
)
from catalog.models import Brand, Category, Product, ProductVariant
from orders.models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    ShippingMethod,
    ShippingRate,
    StockReservation,
)
from orders.serializers import CreateOrderSerializer
from locations.testing import get_test_tehran_city
from payments.models import Payment
from orders.services import (
    ALLOWED_ORDER_TRANSITIONS,
    InvalidOrderStatusTransition,
    cancel_locked_order,
    transition_order_status,
)
from inventory.models import (
    InventoryBatch,
    InventoryDocument,
    InventoryDocumentItem,
    InventoryMovement,
)


class CreateOrderReservationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="test-password",
        )
        self.profile = Profile.objects.create(
            user=self.user,
            mobile="09120000000",
        )
        self.city = get_test_tehran_city()
        self.brand = Brand.objects.create(
            name="Test Brand",
            slug="test-brand",
        )

        self.category = Category.objects.create(
            name="Test Category",
            slug="test-category",
        )

        self.product = Product.objects.create(
            name_fa="محصول آزمایشی",
            slug="test-product",
            brand=self.brand,
            category=self.category,
            description="توضیحات محصول آزمایشی",
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("100000"),
            stock=5,
            shipping_weight_grams=1000,
        )

        self.shipping_method = ShippingMethod.objects.create(
            name="ارسال آزمایشی",
            slug="test-shipping",
        )
        batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="ORDER-TEST-BATCH-001",
            created_by=self.user,
        )

        document = InventoryDocument.objects.create(
            document_number="ORDER-TEST-DOC-001",
            document_type="inbound",
            created_by=self.user,
        )

        item = InventoryDocumentItem.objects.create(
            document=document,
            variant=self.variant,
            batch=batch,
            quantity=5,
            direction="inbound",
        )

        InventoryMovement.objects.create(
            batch=batch,
            document=document,
            document_item=item,
            movement_type="inbound",
            quantity_delta=5,
            created_by=self.user,
        )
        self.shipping_rate = ShippingRate.objects.create(
            method=self.shipping_method,
            province="tehran",
            cost=Decimal("50000"),
        )

    def make_serializer(self, items):
        data = {
            "items": items,
            "shipping_method_slug": "test-shipping",
            "province": "tehran",
            "city_code": self.city.code,
            "address": "آدرس آزمایشی معتبر برای تست سفارش",
            "postal_code": "1234567890",
            "first_name": "Test",
            "last_name": "User",
            "mobile": "09123456789",
            "notes": "",
        }

        request = SimpleNamespace(user=self.user)

        return CreateOrderSerializer(
            data=data,
            context={"request": request},
        )

    def create_profile(self, birth_date=None):
        return Profile.objects.create(
            user=self.user,
            mobile="09120000000",
            birth_date=birth_date,
        )

    def create_order(self, items):
        serializer = self.make_serializer(items)
        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def test_order_reserves_stock_without_decreasing_physical_stock(self):
        order = self.create_order(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 2,
                }
            ]
        )

        self.variant.refresh_from_db()

        reservation = StockReservation.objects.get(order=order)

        self.assertEqual(self.variant.stock, 5)
        self.assertEqual(reservation.quantity, 2)
        self.assertEqual(reservation.status, "active")
        self.assertIsNotNone(order.reservation_expires_at)
        self.assertEqual(
            reservation.expires_at,
            order.reservation_expires_at,
        )

    def test_order_uses_inventory_ledger_instead_of_legacy_stock(self):

        self.variant.stock = 0
        self.variant.save(update_fields=["stock"])

        order = self.create_order(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 2,
                }
            ]
        )

        reservation = StockReservation.objects.get(order=order)

        self.assertEqual(reservation.quantity, 2)
        self.assertEqual(reservation.status, "active")

    def test_duplicate_variant_items_are_aggregated(self):
        order = self.create_order(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 1,
                },
                {
                    "variant_id": self.variant.id,
                    "quantity": 2,
                },
            ]
        )

        reservations = StockReservation.objects.filter(order=order)
        order_items = OrderItem.objects.filter(order=order)

        self.assertEqual(reservations.count(), 1)
        self.assertEqual(reservations.get().quantity, 3)

        self.assertEqual(order_items.count(), 1)
        self.assertEqual(order_items.get().quantity, 3)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)

    def test_active_reservations_reduce_available_stock(self):
        self.create_order(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 3,
                }
            ]
        )

        serializer = self.make_serializer(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 3,
                }
            ]
        )

        serializer.is_valid(raise_exception=True)

        with self.assertRaises(ValidationError):
            serializer.save()

        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(
            StockReservation.objects.filter(status="active").count(),
            1,
        )

    def test_expired_reservation_does_not_reduce_available_stock(self):
        first_order = self.create_order(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 2,
                }
            ]
        )

        old_reservation = StockReservation.objects.get(order=first_order)

        StockReservation.objects.filter(pk=old_reservation.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        second_order = self.create_order(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 5,
                }
            ]
        )

        old_reservation.refresh_from_db()

        self.assertEqual(old_reservation.status, "expired")
        self.assertIsNotNone(old_reservation.released_at)

        new_reservation = StockReservation.objects.get(order=second_order)

        self.assertEqual(new_reservation.quantity, 5)
        self.assertEqual(new_reservation.status, "active")

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)

    def test_order_creation_records_initial_status_history(self):
        order = self.create_order(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 2,
                }
            ]
        )

        history = OrderStatusHistory.objects.get(order=order)

        self.assertEqual(history.old_status, "")
        self.assertEqual(history.new_status, "pending")
        self.assertEqual(history.changed_by, self.user)
        self.assertEqual(history.note, "ایجاد سفارش توسط مشتری.")

    def test_restricted_product_rejects_order_without_birth_date(self):
        self.product.minimum_age = 18
        self.product.save(update_fields=["minimum_age"])

        self.profile.birth_date = None
        self.profile.save(update_fields=["birth_date"])

        serializer = self.make_serializer(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 1,
                }
            ]
        )

        is_valid = serializer.is_valid()

        self.assertFalse(is_valid)
        self.assertIn("items", serializer.errors)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(StockReservation.objects.count(), 0)

    def test_restricted_product_rejects_underage_user(self):
        self.product.minimum_age = 18
        self.product.save(update_fields=["minimum_age"])

        today = timezone.localdate()

        try:
            eighteenth_birthday = today.replace(year=today.year - 18)
        except ValueError:
            eighteenth_birthday = today.replace(
                year=today.year - 18,
                day=28,
            )

        self.profile.birth_date = eighteenth_birthday + timedelta(days=1)
        self.profile.save(update_fields=["birth_date"])

        serializer = self.make_serializer(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 1,
                }
            ]
        )

        is_valid = serializer.is_valid()

        self.assertFalse(is_valid)
        self.assertIn("items", serializer.errors)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(StockReservation.objects.count(), 0)

    def test_restricted_product_accepts_user_on_minimum_age_birthday(self):
        self.product.minimum_age = 18
        self.product.save(update_fields=["minimum_age"])

        today = timezone.localdate()

        try:
            eighteenth_birthday = today.replace(year=today.year - 18)
        except ValueError:
            eighteenth_birthday = today.replace(
                year=today.year - 18,
                day=28,
            )

        self.profile.birth_date = eighteenth_birthday
        self.profile.save(update_fields=["birth_date"])

        order = self.create_order(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 1,
                }
            ]
        )

        self.assertIsNotNone(order.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(StockReservation.objects.filter(order=order).count(), 1)

    def test_unrestricted_product_accepts_user_without_birth_date(self):
        self.product.minimum_age = None
        self.product.save(update_fields=["minimum_age"])

        self.profile.birth_date = None
        self.profile.save(update_fields=["birth_date"])

        order = self.create_order(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 1,
                }
            ]
        )

        self.assertIsNotNone(order.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(StockReservation.objects.filter(order=order).count(), 1)

    def test_restricted_product_accepts_user_above_minimum_age(self):
        self.product.minimum_age = 18
        self.product.save(update_fields=["minimum_age"])

        today = timezone.localdate()

        try:
            eighteenth_birthday = today.replace(year=today.year - 18)
        except ValueError:
            eighteenth_birthday = today.replace(
                year=today.year - 18,
                day=28,
            )

        self.profile.birth_date = eighteenth_birthday - timedelta(days=1)
        self.profile.save(update_fields=["birth_date"])

        order = self.create_order(
            [
                {
                    "variant_id": self.variant.id,
                    "quantity": 1,
                }
            ]
        )

        self.assertIsNotNone(order.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(StockReservation.objects.filter(order=order).count(), 1)

    def test_mixed_order_is_rejected_if_one_product_is_age_restricted(self):
        self.product.minimum_age = None
        self.product.save(update_fields=["minimum_age"])

        restricted_product = Product.objects.create(
            name_fa="محصول محدودیت سنی",
            slug="age-restricted-product",
            brand=self.brand,
            category=self.category,
            description="محصول آزمایشی با محدودیت سنی",
            minimum_age=18,
        )

        restricted_variant = ProductVariant.objects.create(
            product=restricted_product,
            price=Decimal("150000"),
            stock=5,
        )

        batch = InventoryBatch.objects.create(
            variant=restricted_variant,
            batch_number="AGE-TEST-BATCH-001",
            created_by=self.user,
        )

        document = InventoryDocument.objects.create(
            document_number="AGE-TEST-DOC-001",
            document_type="inbound",
            created_by=self.user,
        )

        item = InventoryDocumentItem.objects.create(
            document=document,
            variant=restricted_variant,
            batch=batch,
            quantity=5,
            direction="inbound",
        )

        InventoryMovement.objects.create(
            batch=batch,
            document=document,
            document_item=item,
            movement_type="inbound",
            quantity_delta=5,
            created_by=self.user,
        )

        today = timezone.localdate()
        try:
            eighteenth_birthday = today.replace(year=today.year - 18)
        except ValueError:
            eighteenth_birthday = today.replace(
                year=today.year - 18,
                day=28,
            )

        self.profile.birth_date = eighteenth_birthday + timedelta(days=1)
        self.profile.save(update_fields=["birth_date"])

        serializer = self.make_serializer(
            [
                {"variant_id": self.variant.id, "quantity": 1},
                {"variant_id": restricted_variant.id, "quantity": 1},
            ]
        )

        is_valid = serializer.is_valid()

        self.assertFalse(is_valid)
        self.assertIn("items", serializer.errors)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(StockReservation.objects.count(), 0)

class CancelOrderTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="cancel-user",
            password="test-password",
        )

        self.other_user = User.objects.create_user(
            username="other-user",
            password="test-password",
        )

        brand = Brand.objects.create(
            name="Cancel Brand",
            slug="cancel-brand",
        )

        category = Category.objects.create(
            name="Cancel Category",
            slug="cancel-category",
        )

        product = Product.objects.create(
            name_fa="محصول لغو آزمایشی",
            slug="cancel-product",
            brand=brand,
            category=category,
            description="توضیحات تست",
        )

        self.variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=5,
        )

        self.order = Order.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            mobile="09123456789",
            province="tehran",
            city="تهران",
            address="آدرس آزمایشی معتبر",
            subtotal=Decimal("200000"),
            vat_amount=Decimal("20000"),
            total_amount=Decimal("270000"),
            status="pending",
            reservation_expires_at=timezone.now() + timedelta(minutes=30),
        )

        self.payment = Payment.objects.create(
            order=self.order,
            gateway="mock",
            amount=self.order.total_amount,
            status="pending",
        )

        OrderItem.objects.create(
            order=self.order,
            variant=self.variant,
            product_name="محصول لغو آزمایشی",
            product_slug="cancel-product",
            brand_name="Cancel Brand",
            variant_label="تنوع آزمایشی",
            price=Decimal("100000"),
            quantity=2,
            subtotal=Decimal("200000"),
        )

        self.reservation = StockReservation.objects.create(
            order=self.order,
            variant=self.variant,
            quantity=2,
            status="active",
            expires_at=self.order.reservation_expires_at,
        )

        self.cancel_url = reverse(
            "cancel-order",
            args=[self.order.order_number],
        )

        self.client.force_authenticate(user=self.user)

    def test_owner_can_cancel_pending_order(self):
        self.payment.status = "failed"
        self.payment.save(update_fields=["status"])
        response = self.client.post(self.cancel_url)

        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        self.reservation.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.payment.status, "failed")
        self.assertEqual(self.reservation.status, "released")
        self.assertIsNotNone(self.reservation.released_at)

        # Physical stock must not change.
        self.assertEqual(self.variant.stock, 5)

        history = OrderStatusHistory.objects.get(order=self.order)

        self.assertEqual(history.old_status, "pending")
        self.assertEqual(history.new_status, "cancelled")
        self.assertEqual(history.changed_by, self.user)
        self.assertEqual(
            history.note,
            "لغو سفارش به درخواست مشتری.",
        )

    def test_owner_can_cancel_order_with_initiating_payment(self):
        self.payment.status = "initiating"
        self.payment.save(update_fields=["status"])

        response = self.client.post(self.cancel_url)

        self.assertEqual(response.status_code, 409)

        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.reservation.refresh_from_db()

        self.assertEqual(self.order.status, "pending")
        self.assertEqual(self.payment.status, "initiating")
        self.assertEqual(self.reservation.status, "active")

    def test_owner_can_cancel_order_with_unknown_payment(self):
        self.payment.status = "unknown"
        self.payment.save(update_fields=["status"])

        response = self.client.post(self.cancel_url)

        self.assertEqual(response.status_code, 409)

        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.reservation.refresh_from_db()

        self.assertEqual(self.order.status, "pending")
        self.assertEqual(self.payment.status, "unknown")
        self.assertEqual(self.reservation.status, "active")

    def test_owner_can_cancel_order_with_verifying_payment(self):
        self.payment.status = "verifying"
        self.payment.save(update_fields=["status"])

        response = self.client.post(self.cancel_url)

        self.assertEqual(response.status_code, 409)

        self.order.refresh_from_db()
        self.payment.refresh_from_db()
        self.reservation.refresh_from_db()

        self.assertEqual(self.order.status, "pending")
        self.assertEqual(self.payment.status, "verifying")
        self.assertEqual(self.reservation.status, "active")

    def test_another_user_cannot_cancel_order(self):
        self.client.force_authenticate(user=self.other_user)

        response = self.client.post(self.cancel_url)

        self.assertEqual(response.status_code, 404)

        self.order.refresh_from_db()
        self.reservation.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.payment.status, "pending")
        self.assertEqual(self.order.status, "pending")
        self.assertEqual(self.reservation.status, "active")

    def test_paid_order_cannot_be_cancelled(self):
        self.order.status = "paid"
        self.order.save(update_fields=["status"])

        response = self.client.post(self.cancel_url)

        self.assertEqual(response.status_code, 400)

        self.order.refresh_from_db()
        self.reservation.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.payment.status, "pending")
        self.assertEqual(self.order.status, "paid")
        self.assertEqual(self.reservation.status, "active")
        self.assertIsNone(self.reservation.released_at)

    def test_repeated_cancellation_does_not_release_reservation_twice(self):
        self.payment.status = "failed"
        self.payment.save(update_fields=["status"])
        first_response = self.client.post(self.cancel_url)

        self.assertEqual(first_response.status_code, 200)

        self.reservation.refresh_from_db()
        first_released_at = self.reservation.released_at

        second_response = self.client.post(self.cancel_url)

        self.assertEqual(second_response.status_code, 400)

        self.order.refresh_from_db()
        self.reservation.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.payment.status, "failed")
        self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(self.reservation.status, "released")
        self.assertEqual(
            self.reservation.released_at,
            first_released_at,
        )


class ExpireOrdersCommandTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="expire-user",
            password="test-password",
        )

        brand = Brand.objects.create(
            name="Expire Brand",
            slug="expire-brand",
        )

        category = Category.objects.create(
            name="Expire Category",
            slug="expire-category",
        )

        product = Product.objects.create(
            name_fa="محصول انقضا آزمایشی",
            slug="expire-product",
            brand=brand,
            category=category,
            description="توضیحات تست انقضا",
        )

        self.variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=5,
        )

    def create_order_with_reservation(self, expires_delta):
        expires_at = timezone.now() + expires_delta

        order = Order.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            mobile="09123456789",
            province="tehran",
            city="تهران",
            address="آدرس آزمایشی معتبر",
            subtotal=Decimal("200000"),
            vat_amount=Decimal("20000"),
            total_amount=Decimal("270000"),
            status="pending",
            reservation_expires_at=expires_at,
        )

        reservation = StockReservation.objects.create(
            order=order,
            variant=self.variant,
            quantity=2,
            status="active",
            expires_at=expires_at,
        )

        return order, reservation

    def create_payment(self, order, status="pending"):
        return Payment.objects.create(
            order=order,
            gateway="mock",
            amount=order.total_amount,
            status=status,
        )

    def run_expire_command(self):
        output = StringIO()
        call_command("expire_orders", stdout=output)
        return output.getvalue()

    def test_expired_order_with_pending_payment_keeps_reservation(self):
        order, reservation = self.create_order_with_reservation(
            timedelta(minutes=-5),
        )
        payment = self.create_payment(order, status="pending")
        output = self.run_expire_command()

        order.refresh_from_db()
        reservation.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(order.status, "pending")
        self.assertEqual(reservation.status, "active")
        self.assertIsNone(reservation.released_at)
        self.assertEqual(payment.status, "pending")

        self.assertIn("Expired orders: 0", output)
        self.assertIn("Cancelled active payments: 0", output)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)

        self.assertFalse(OrderStatusHistory.objects.filter(order=order).exists())

    def test_expiration_does_not_cancel_unresolved_payments(self):
        for status in ("initiating", "verifying", "unknown"):
            with self.subTest(payment_status=status):
                order, reservation = self.create_order_with_reservation(
                    timedelta(minutes=-5),
                )
                payment = self.create_payment(order, status=status)

                output = self.run_expire_command()

                order.refresh_from_db()
                reservation.refresh_from_db()
                payment.refresh_from_db()

                self.assertEqual(order.status, "pending")
                self.assertEqual(reservation.status, "active")
                self.assertIsNone(reservation.released_at)
                self.assertEqual(payment.status, status)

                self.assertIn("Expired orders: 0", output)

    def test_expiration_command_is_idempotent(self):
        order, reservation = self.create_order_with_reservation(
            timedelta(minutes=-5),
        )
        payment = self.create_payment(order, status="failed")

        self.run_expire_command()

        reservation.refresh_from_db()
        payment.refresh_from_db()

        first_released_at = reservation.released_at
        first_gateway_response = payment.gateway_response

        output = self.run_expire_command()

        order.refresh_from_db()
        reservation.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(order.status, "cancelled")
        self.assertEqual(reservation.status, "expired")
        self.assertEqual(reservation.released_at, first_released_at)
        self.assertEqual(payment.status, "failed")
        self.assertEqual(payment.gateway_response, first_gateway_response)

        self.assertIn("Expired orders: 0", output)
        self.assertIn("Cancelled active payments: 0", output)

    def test_non_expired_order_is_not_changed(self):
        order, reservation = self.create_order_with_reservation(
            timedelta(minutes=30),
        )
        payment = self.create_payment(order)

        self.run_expire_command()

        order.refresh_from_db()
        reservation.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(order.status, "pending")
        self.assertEqual(reservation.status, "active")
        self.assertIsNone(reservation.released_at)
        self.assertEqual(payment.status, "pending")

    def test_paid_order_is_not_changed(self):
        order, reservation = self.create_order_with_reservation(
            timedelta(minutes=-5),
        )
        order.status = "paid"
        order.save(update_fields=["status"])

        payment = self.create_payment(order, status="success")

        self.run_expire_command()

        order.refresh_from_db()
        reservation.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(order.status, "paid")
        self.assertEqual(reservation.status, "active")
        self.assertIsNone(reservation.released_at)
        self.assertEqual(payment.status, "success")

    def test_failed_payment_is_not_changed_when_order_expires(self):
        order, reservation = self.create_order_with_reservation(
            timedelta(minutes=-5),
        )
        payment = self.create_payment(order, status="failed")

        self.run_expire_command()

        order.refresh_from_db()
        reservation.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(order.status, "cancelled")
        self.assertEqual(reservation.status, "expired")
        self.assertEqual(payment.status, "failed")


class OrderStatusTransitionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="status-user",
            password="test-password",
        )

        self.order = Order.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            mobile="09123456789",
            province="tehran",
            city="تهران",
            address="آدرس آزمایشی معتبر",
            subtotal=Decimal("200000"),
            vat_amount=Decimal("20000"),
            total_amount=Decimal("270000"),
            status="pending",
        )

    def test_valid_transition_creates_history(self):
        changed = transition_order_status(
            order=self.order,
            new_status="paid",
            changed_by=self.user,
            note="تست تغییر وضعیت",
        )

        self.assertTrue(changed)

        self.order.refresh_from_db()

        history = OrderStatusHistory.objects.get(order=self.order)

        self.assertEqual(self.order.status, "paid")
        self.assertEqual(history.old_status, "pending")
        self.assertEqual(history.new_status, "paid")
        self.assertEqual(history.changed_by, self.user)
        self.assertEqual(history.note, "تست تغییر وضعیت")

    def test_invalid_transition_is_rejected(self):
        with self.assertRaises(InvalidOrderStatusTransition):
            transition_order_status(
                order=self.order,
                new_status="shipped",
            )

        self.order.refresh_from_db()

        self.assertEqual(self.order.status, "pending")
        self.assertEqual(
            OrderStatusHistory.objects.filter(order=self.order).count(),
            0,
        )

    def test_unknown_status_is_rejected(self):
        with self.assertRaises(InvalidOrderStatusTransition):
            transition_order_status(
                order=self.order,
                new_status="unknown",
            )

        self.order.refresh_from_db()

        self.assertEqual(self.order.status, "pending")

    def test_same_status_does_not_create_duplicate_history(self):
        changed = transition_order_status(
            order=self.order,
            new_status="pending",
        )

        self.assertFalse(changed)
        self.assertEqual(
            OrderStatusHistory.objects.filter(order=self.order).count(),
            0,
        )

    @patch(
        "orders.services.transition_order_status",
        side_effect=RuntimeError("forced failure"),
    )
    def test_cancel_locked_order_rolls_back_reservation_release(
        self,
        mocked_transition,
    ):
        now = timezone.now()

        reservation = StockReservation.objects.create(
            order=self.order,
            variant=ProductVariant.objects.create(
                product=Product.objects.create(
                    name_fa="محصول آزمایشی بازگشت",
                    slug="rollback-product",
                    brand=Brand.objects.create(
                        name="Rollback Brand",
                        slug="rollback-brand",
                    ),
                    category=Category.objects.create(
                        name="Rollback Category",
                        slug="rollback-category",
                    ),
                    description="Rollback test product",
                ),
                price=Decimal("100000"),
                stock=5,
            ),
            quantity=2,
            status="active",
            expires_at=now + timedelta(minutes=30),
        )

        with self.assertRaises(RuntimeError):
            cancel_locked_order(
                order=self.order,
                reservations=[reservation],
                now=now,
                note="Rollback test",
            )

        reservation.refresh_from_db()
        self.order.refresh_from_db()

        self.assertEqual(reservation.status, "active")
        self.assertIsNone(reservation.released_at)
        self.assertEqual(self.order.status, "pending")
        self.assertEqual(
            OrderStatusHistory.objects.filter(order=self.order).count(),
            0,
        )

    def test_cancel_locked_order_releases_active_reservation(self):
        now = timezone.now()

        brand = Brand.objects.create(
            name="Success Brand",
            slug="success-brand",
        )
        category = Category.objects.create(
            name="Success Category",
            slug="success-category",
        )
        product = Product.objects.create(
            name_fa="محصول لغو موفق",
            slug="success-product",
            brand=brand,
            category=category,
            description="Cancellation test product",
        )
        variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=5,
        )
        reservation = StockReservation.objects.create(
            order=self.order,
            variant=variant,
            quantity=2,
            status="active",
            expires_at=now + timedelta(minutes=30),
        )

        changed = cancel_locked_order(
            order=self.order,
            reservations=[reservation],
            now=now,
            changed_by=self.user,
            note="Successful cancellation test",
        )

        self.assertTrue(changed)

        self.order.refresh_from_db()
        reservation.refresh_from_db()

        self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(reservation.status, "released")
        self.assertEqual(reservation.released_at, now)

        history = OrderStatusHistory.objects.get(order=self.order)
        self.assertEqual(history.old_status, "pending")
        self.assertEqual(history.new_status, "cancelled")
        self.assertEqual(history.changed_by, self.user)

    def test_cancel_locked_order_expires_already_expired_reservation(self):
        now = timezone.now()

        brand = Brand.objects.create(
            name="Expired Brand",
            slug="expired-brand",
        )
        category = Category.objects.create(
            name="Expired Category",
            slug="expired-category",
        )
        product = Product.objects.create(
            name_fa="محصول رزرو منقضی",
            slug="expired-product",
            brand=brand,
            category=category,
            description="Expired reservation test product",
        )
        variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=5,
        )
        reservation = StockReservation.objects.create(
            order=self.order,
            variant=variant,
            quantity=2,
            status="active",
            expires_at=now - timedelta(minutes=5),
        )

        changed = cancel_locked_order(
            order=self.order,
            reservations=[reservation],
            now=now,
            changed_by=self.user,
            note="Expired reservation test",
        )

        self.assertTrue(changed)

        self.order.refresh_from_db()
        reservation.refresh_from_db()

        self.assertEqual(self.order.status, "cancelled")
        self.assertEqual(reservation.status, "expired")
        self.assertEqual(reservation.released_at, now)


class OrderAdminStatusActionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="order-manager",
            password="test-password",
            is_staff=True,
        )

        self.change_permission = Permission.objects.get(
            content_type__app_label="orders",
            codename="change_order",
        )

        self.manage_permission = Permission.objects.get(
            content_type__app_label="orders",
            codename="can_manage_order_status",
        )

        self.user.user_permissions.add(
            self.change_permission,
            self.manage_permission,
        )

        self.order = Order.objects.create(
            user=self.user,
            first_name="Test",
            last_name="Manager",
            mobile="09123456789",
            province="tehran",
            city="تهران",
            address="آدرس آزمایشی معتبر",
            subtotal=Decimal("200000"),
            vat_amount=Decimal("20000"),
            total_amount=Decimal("270000"),
            status="paid",
        )

        self.changelist_url = reverse("admin:orders_order_changelist")

    def post_admin_action(self, action, order):
        return self.client.post(
            self.changelist_url,
            {
                "action": action,
                "index": "0",
                "_selected_action": [str(order.pk)],
                "select_across": "0",
            },
        )

    def test_authorized_user_can_complete_valid_status_transitions(self):
        self.client.force_login(self.user)

        response = self.post_admin_action("mark_processing", self.order)
        self.assertEqual(response.status_code, 302)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "processing")

        response = self.post_admin_action("mark_shipped", self.order)
        self.assertEqual(response.status_code, 302)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "shipped")

        response = self.post_admin_action("mark_delivered", self.order)
        self.assertEqual(response.status_code, 302)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "delivered")

        history = OrderStatusHistory.objects.filter(order=self.order).order_by("id")

        self.assertEqual(history.count(), 3)

        self.assertEqual(
            list(history.values_list("new_status", flat=True)),
            ["processing", "shipped", "delivered"],
        )

        for record in history:
            self.assertEqual(record.changed_by, self.user)

    def test_unauthorized_user_cannot_change_order_status(self):
        unauthorized_user = User.objects.create_user(
            username="unauthorized-manager",
            password="test-password",
            is_staff=True,
        )

        unauthorized_user.user_permissions.add(
            self.change_permission,
        )

        self.client.force_login(unauthorized_user)

        self.post_admin_action("mark_processing", self.order)

        self.order.refresh_from_db()

        self.assertEqual(self.order.status, "paid")
        self.assertEqual(
            OrderStatusHistory.objects.filter(order=self.order).count(),
            0,
        )

    def test_invalid_admin_transition_does_not_change_order(self):
        self.client.force_login(self.user)

        self.order.status = "pending"
        self.order.save(update_fields=["status"])

        self.post_admin_action("mark_shipped", self.order)

        self.order.refresh_from_db()

        self.assertEqual(self.order.status, "pending")
        self.assertEqual(
            OrderStatusHistory.objects.filter(order=self.order).count(),
            0,
        )
