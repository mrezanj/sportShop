from datetime import timedelta
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from catalog.models import Brand, Category, Product, ProductVariant
from orders.models import (
    Order,
    OrderItem,
    ShippingMethod,
    ShippingRate,
    StockReservation,
)
from orders.serializers import CreateOrderSerializer
from payments.models import Payment


class CreateOrderReservationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
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
        )

        self.shipping_method = ShippingMethod.objects.create(
            name="ارسال آزمایشی",
            slug="test-shipping",
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
            "city": "تهران",
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
        response = self.client.post(self.cancel_url)

        self.assertEqual(response.status_code, 200)

        self.order.refresh_from_db()
        self.reservation.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.payment.status, "cancelled")
        self.assertEqual(
            self.payment.gateway_response,
            {"reason": "order_cancelled"},
        )
        self.assertEqual(self.reservation.status, "released")
        self.assertIsNotNone(self.reservation.released_at)

        # Physical stock must not change.
        self.assertEqual(self.variant.stock, 5)

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
        first_response = self.client.post(self.cancel_url)

        self.assertEqual(first_response.status_code, 200)

        self.reservation.refresh_from_db()
        first_released_at = self.reservation.released_at

        second_response = self.client.post(self.cancel_url)

        self.assertEqual(second_response.status_code, 400)

        self.order.refresh_from_db()
        self.reservation.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertEqual(self.payment.status, "cancelled")
        self.assertEqual(
            self.payment.gateway_response,
            {"reason": "order_cancelled"},
        )
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

    def test_expired_order_releases_reservation_and_cancels_pending_payment(self):
        order, reservation = self.create_order_with_reservation(
            timedelta(minutes=-5),
        )
        payment = self.create_payment(order)

        output = self.run_expire_command()

        order.refresh_from_db()
        reservation.refresh_from_db()
        payment.refresh_from_db()

        self.assertEqual(order.status, "cancelled")
        self.assertEqual(reservation.status, "expired")
        self.assertIsNotNone(reservation.released_at)

        self.assertEqual(payment.status, "cancelled")
        self.assertEqual(
            payment.gateway_response,
            {"reason": "order_expired"},
        )

        self.assertIn("Expired orders: 1", output)
        self.assertIn("Cancelled pending payments: 1", output)

        # Expiring an order must not change physical stock.
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)

    def test_expiration_command_is_idempotent(self):
        order, reservation = self.create_order_with_reservation(
            timedelta(minutes=-5),
        )
        payment = self.create_payment(order)

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
        self.assertEqual(payment.status, "cancelled")
        self.assertEqual(payment.gateway_response, first_gateway_response)

        self.assertIn("Expired orders: 0", output)
        self.assertIn("Cancelled pending payments: 0", output)

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
