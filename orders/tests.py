
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from catalog.models import Brand, Category, Product, ProductVariant
from orders.models import (
    Order,
    OrderItem,
    ShippingMethod,
    ShippingRate,
    StockReservation,
)
from orders.serializers import CreateOrderSerializer


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
