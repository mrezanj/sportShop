from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from rest_framework.test import APIClient

from catalog.models import Brand, Category, Product, ProductVariant
from orders.models import (
    Order,
    OrderStatusHistory,
    ShippingMethod,
    ShippingRate,
    StockReservation,
)
from orders.serializers import CreateOrderSerializer
from payments.models import Payment


class PaymentFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="payment-user",
            password="test-password",
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        brand = Brand.objects.create(
            name="Test Brand",
            slug="test-brand",
        )

        category = Category.objects.create(
            name="Test Category",
            slug="test-category",
        )

        product = Product.objects.create(
            name_fa="محصول آزمایشی",
            slug="payment-test-product",
            brand=brand,
            category=category,
            description="توضیحات محصول آزمایشی",
        )

        self.variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=5,
        )

        shipping_method = ShippingMethod.objects.create(
            name="ارسال آزمایشی",
            slug="payment-test-shipping",
        )

        ShippingRate.objects.create(
            method=shipping_method,
            province="tehran",
            cost=Decimal("50000"),
        )

    def create_order(self, quantity=2):
        data = {
            "items": [
                {
                    "variant_id": self.variant.id,
                    "quantity": quantity,
                }
            ],
            "shipping_method_slug": "payment-test-shipping",
            "province": "tehran",
            "city": "تهران",
            "address": "آدرس آزمایشی معتبر برای تست پرداخت",
            "postal_code": "1234567890",
            "first_name": "Test",
            "last_name": "User",
            "mobile": "09123456789",
            "notes": "",
        }

        serializer = CreateOrderSerializer(
            data=data,
            context={"request": SimpleNamespace(user=self.user)},
        )

        serializer.is_valid(raise_exception=True)
        return serializer.save()

    def initiate(self, order):
        return self.client.post(
            "/api/payments/initiate/",
            {"order_number": order.order_number},
            format="json",
        )

    def verify(self, order, authority, status="success"):
        return self.client.post(
            "/api/payments/verify/",
            {
                "order_number": order.order_number,
                "authority": authority,
                "status": status,
            },
            format="json",
        )

    def start_payment(self, order):
        response = self.initiate(order)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

        payment = Payment.objects.get(pk=response.data["payment_id"])

        return payment

    def test_successful_payment_consumes_reservation_and_stock(self):
        order = self.create_order(quantity=2)
        reservation = StockReservation.objects.get(order=order)

        payment = self.start_payment(order)

        response = self.verify(order, payment.authority)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

        order.refresh_from_db()
        payment.refresh_from_db()
        reservation.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(order.status, "paid")
        histories = OrderStatusHistory.objects.filter(order=order).order_by("id")

        self.assertEqual(histories.count(), 2)

        initial_history = histories.first()
        payment_history = histories.last()

        self.assertEqual(initial_history.old_status, "")
        self.assertEqual(initial_history.new_status, "pending")
        self.assertEqual(initial_history.changed_by, self.user)

        self.assertEqual(payment_history.old_status, "pending")
        self.assertEqual(payment_history.new_status, "paid")
        self.assertIsNone(payment_history.changed_by)
        self.assertEqual(
            payment_history.note,
            "پرداخت سفارش با موفقیت تأیید شد.",
        )

        self.assertEqual(payment.status, "success")
        self.assertEqual(reservation.status, "consumed")
        self.assertIsNotNone(reservation.consumed_at)
        self.assertEqual(self.variant.stock, 3)

    def test_repeated_callback_does_not_decrease_stock_twice(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        first_response = self.verify(order, payment.authority)

        self.assertEqual(first_response.status_code, 200)
        self.assertTrue(first_response.data["success"])

        second_response = self.verify(order, payment.authority)

        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(second_response.data["already_paid"])

        self.variant.refresh_from_db()

        self.assertEqual(self.variant.stock, 3)
        self.assertEqual(
            StockReservation.objects.filter(
                order=order,
                status="consumed",
            ).count(),
            1,
        )

    def test_failed_payment_keeps_reservation_for_retry(self):
        order = self.create_order(quantity=2)
        reservation = StockReservation.objects.get(order=order)

        first_payment = self.start_payment(order)

        response = self.verify(
            order,
            first_payment.authority,
            status="failed",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["success"])

        first_payment.refresh_from_db()
        reservation.refresh_from_db()

        self.assertEqual(first_payment.status, "failed")
        self.assertEqual(reservation.status, "active")

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)

        second_payment = self.start_payment(order)

        self.assertNotEqual(first_payment.id, second_payment.id)

        success_response = self.verify(
            order,
            second_payment.authority,
        )

        self.assertEqual(success_response.status_code, 200)
        self.assertTrue(success_response.data["success"])

        order.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(order.status, "paid")
        self.assertEqual(self.variant.stock, 3)

    def test_expired_reservation_cannot_be_paid(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        expired_at = timezone.now() - timedelta(minutes=1)

        Order.objects.filter(pk=order.pk).update(reservation_expires_at=expired_at)

        StockReservation.objects.filter(order=order).update(expires_at=expired_at)

        response = self.verify(order, payment.authority)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])

        order.refresh_from_db()
        payment.refresh_from_db()

        reservation = StockReservation.objects.get(order=order)

        self.assertEqual(order.status, "cancelled")
        self.assertEqual(payment.status, "cancelled")
        self.assertEqual(reservation.status, "expired")
        self.assertIsNotNone(reservation.released_at)

        self.variant.refresh_from_db()
        self.assertEqual(self.variant.stock, 5)

    def test_initiating_payment_for_expired_order_cancels_it(self):
        order = self.create_order(quantity=2)

        expired_at = timezone.now() - timedelta(minutes=1)

        Order.objects.filter(pk=order.pk).update(reservation_expires_at=expired_at)

        StockReservation.objects.filter(order=order).update(expires_at=expired_at)

        response = self.initiate(order)

        self.assertEqual(response.status_code, 400)

        order.refresh_from_db()
        reservation = StockReservation.objects.get(order=order)

        self.assertEqual(order.status, "cancelled")
        self.assertEqual(reservation.status, "expired")
        self.assertEqual(Payment.objects.filter(order=order).count(), 0)

    def test_payment_amount_mismatch_is_rejected(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        Payment.objects.filter(pk=payment.pk).update(amount=Decimal("150000"))

        response = self.verify(order, payment.authority)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])

        order.refresh_from_db()
        payment.refresh_from_db()
        reservation = StockReservation.objects.get(order=order)
        self.variant.refresh_from_db()

        self.assertEqual(order.status, "pending")
        self.assertEqual(payment.status, "failed")
        self.assertEqual(reservation.status, "active")
        self.assertEqual(self.variant.stock, 5)

    def test_invalid_authority_does_not_process_payment(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        response = self.verify(
            order,
            "INVALID-AUTHORITY",
        )

        self.assertEqual(response.status_code, 400)

        order.refresh_from_db()
        payment.refresh_from_db()
        self.variant.refresh_from_db()

        reservation = StockReservation.objects.get(order=order)

        self.assertEqual(order.status, "pending")
        self.assertEqual(payment.status, "pending")
        self.assertEqual(reservation.status, "active")
        self.assertEqual(self.variant.stock, 5)
