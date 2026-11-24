from datetime import timedelta
from io import StringIO
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch
from django.db import connection, close_old_connections
from django.db.models import Sum
from django.test import TransactionTestCase
from payments.gateways.base import PaymentResult
from django.contrib.auth.models import User
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
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
from orders.shipping_preview import ShippingPreviewSerializer
from locations.testing import get_test_tehran_city
from orders.services import cancel_locked_order
from payments.gateways import get_gateway
from payments.models import Payment, MockGatewayTransaction
from payments.views import mock_payment_page
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from inventory.models import (
    InventoryBatch,
    InventoryDocument,
    InventoryDocumentItem,
    InventoryMovement,
)


def create_inventory_ledger_for_variant(variant, user, quantity=5):
    batch = InventoryBatch.objects.create(
        variant=variant,
        batch_number=f"PAYMENT-TEST-BATCH-{variant.pk}",
        created_by=user,
    )

    document = InventoryDocument.objects.create(
        document_number=f"PAYMENT-TEST-IN-{variant.pk}",
        document_type="inbound",
        created_by=user,
    )

    item = InventoryDocumentItem.objects.create(
        document=document,
        variant=variant,
        batch=batch,
        quantity=quantity,
        direction="inbound",
    )

    InventoryMovement.objects.create(
        batch=batch,
        document=document,
        document_item=item,
        movement_type="inbound",
        quantity_delta=quantity,
        created_by=user,
    )



def attach_checkout_quote(data, user):
    preview = ShippingPreviewSerializer(
        data={
            "items": data["items"],
            "shipping_method_slug": data["shipping_method_slug"],
            "province": data["province"],
            "city_code": data["city_code"],
        },
        context={"request": SimpleNamespace(user=user)},
    )
    preview.is_valid(raise_exception=True)
    data["quote_token"] = preview.validated_data["_result"]["quote_token"]
    return data


@override_settings(DEBUG=True, ACTIVE_PAYMENT_GATEWAY="mock")
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
            shipping_weight_grams=1000,
        )
        self.batch = InventoryBatch.objects.create(
            variant=self.variant,
            batch_number="PAYMENT-TEST-BATCH",
            created_by=self.user,
        )

        document = InventoryDocument.objects.create(
            document_number="PAYMENT-TEST-IN-001",
            document_type="inbound",
            created_by=self.user,
        )

        item = InventoryDocumentItem.objects.create(
            document=document,
            variant=self.variant,
            batch=self.batch,
            quantity=5,
            direction="inbound",
        )

        InventoryMovement.objects.create(
            batch=self.batch,
            document=document,
            document_item=item,
            movement_type="inbound",
            quantity_delta=5,
            created_by=self.user,
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

    def get_batch_physical_quantity(self):
        return (
            InventoryMovement.objects.filter(batch=self.batch).aggregate(
                total=Sum("quantity_delta")
            )["total"]
            or 0
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
            "city_code": get_test_tehran_city().code,
            "address": "آدرس آزمایشی معتبر برای تست پرداخت",
            "postal_code": "1234567890",
            "first_name": "Test",
            "last_name": "User",
            "mobile": "09123456789",
            "notes": "",
        }

        data = attach_checkout_quote(data, self.user)
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

    def recover(self, order):
        return self.client.post(
            "/api/payments/recover/",
            {"order_number": order.order_number},
            format="json",
        )

    def start_payment(self, order):
        response = self.initiate(order)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

        payment = Payment.objects.get(pk=response.data["payment_id"])

        return payment

    def test_repeated_initiation_reuses_pending_payment(self):
        order = self.create_order(quantity=2)

        first_response = self.initiate(order)

        self.assertEqual(first_response.status_code, 200)
        self.assertTrue(first_response.data["success"])

        first_payment = Payment.objects.get(pk=first_response.data["payment_id"])
        first_authority = first_payment.authority
        first_redirect_url = first_response.data["redirect_url"]

        second_response = self.initiate(order)

        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(second_response.data["success"])

        self.assertEqual(
            second_response.data["payment_id"],
            first_payment.id,
        )
        self.assertEqual(
            second_response.data["redirect_url"],
            first_redirect_url,
        )

        first_payment.refresh_from_db()

        self.assertEqual(first_payment.authority, first_authority)
        self.assertEqual(
            Payment.objects.filter(order=order).count(),
            1,
        )

    def test_recover_unknown_payment_restores_pending_session(self):
        order = self.create_order(quantity=2)

        gateway = SimpleNamespace(
            request=Mock(
                return_value=PaymentResult(
                    success=False,
                    message="Gateway response is unknown.",
                    raw_response={
                        "step": "request",
                        "error": "connection_timeout",
                    },
                    outcome_unknown=True,
                )
            )
        )

        with patch("payments.views.get_gateway", return_value=gateway):
            response = self.initiate(order)

        self.assertEqual(response.status_code, 409)

        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.status, "unknown")

        payment.request_started_at = timezone.now() - timedelta(minutes=3)
        payment.save(update_fields=["request_started_at"])

        recovered_gateway = SimpleNamespace(
            inquire=Mock(
                return_value=PaymentResult(
                    success=True,
                    authority="MOCK-RECOVERED-123",
                    redirect_url="http://testserver/mock-payment/123/",
                    message="Mock payment session recovered",
                    raw_response={
                        "step": "inquire",
                    },
                )
            )
        )

        with patch(
            "payments.views.get_gateway",
            return_value=recovered_gateway,
        ):
            recovery_response = self.recover(order)

        self.assertEqual(recovery_response.status_code, 200)
        self.assertTrue(recovery_response.data["success"])
        self.assertTrue(recovery_response.data["recovered"])

        payment.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(payment.status, "pending")
        self.assertEqual(
            payment.authority,
            "MOCK-RECOVERED-123",
        )
        self.assertEqual(order.status, "pending")
        self.assertEqual(
            Payment.objects.filter(order=order).count(),
            1,
        )
        recovered_gateway.inquire.assert_called_once()

    def test_recover_request_does_not_restore_session_for_cancelled_order(self):
        order = self.create_order(quantity=2)

        gateway = SimpleNamespace(
            request=Mock(
                return_value=PaymentResult(
                    success=False,
                    outcome_unknown=True,
                    raw_response={"step": "request"},
                )
            )
        )

        with patch("payments.views.get_gateway", return_value=gateway):
            response = self.initiate(order)

        self.assertEqual(response.status_code, 409)

        payment = Payment.objects.get(order=order)
        payment.request_started_at = timezone.now() - timedelta(minutes=3)
        payment.save(update_fields=["request_started_at"])

        cancel_locked_order(
            order,
            list(StockReservation.objects.filter(order=order)),
            now=timezone.now(),
            changed_by=self.user,
            note="Test cancellation",
        )

        recovered_gateway = SimpleNamespace(
            inquire=Mock(
                return_value=PaymentResult(
                    success=True,
                    authority="MOCK-CANCELLED-123",
                    redirect_url="http://testserver/mock-payment/123/",
                )
            )
        )

        with patch(
            "payments.views.get_gateway",
            return_value=recovered_gateway,
        ):
            recovery_response = self.recover(order)

        self.assertEqual(recovery_response.status_code, 409)
        self.assertNotIn("redirect_url", recovery_response.data)

        payment.refresh_from_db()
        order.refresh_from_db()
        reservation = StockReservation.objects.get(order=order)

        self.assertEqual(order.status, "cancelled")
        self.assertEqual(payment.status, "unknown")
        self.assertNotEqual(payment.authority, "MOCK-CANCELLED-123")
        self.assertEqual(reservation.status, "released")
        recovered_gateway.inquire.assert_called_once()

    def test_recover_request_does_not_restore_session_for_expired_reservation(self):
        order = self.create_order(quantity=2)

        gateway = SimpleNamespace(
            request=Mock(
                return_value=PaymentResult(
                    success=False,
                    outcome_unknown=True,
                    raw_response={"step": "request"},
                )
            )
        )

        with patch("payments.views.get_gateway", return_value=gateway):
            response = self.initiate(order)

        self.assertEqual(response.status_code, 409)

        payment = Payment.objects.get(order=order)
        payment.request_started_at = timezone.now() - timedelta(minutes=3)
        payment.save(update_fields=["request_started_at"])

        expired_at = timezone.now() - timedelta(minutes=1)

        Order.objects.filter(pk=order.pk).update(reservation_expires_at=expired_at)
        StockReservation.objects.filter(order=order).update(expires_at=expired_at)

        recovered_gateway = SimpleNamespace(
            inquire=Mock(
                return_value=PaymentResult(
                    success=True,
                    authority="MOCK-EXPIRED-123",
                    redirect_url="http://testserver/mock-payment/123/",
                )
            )
        )

        with patch(
            "payments.views.get_gateway",
            return_value=recovered_gateway,
        ):
            recovery_response = self.recover(order)

        self.assertEqual(recovery_response.status_code, 409)
        self.assertNotIn("redirect_url", recovery_response.data)

        payment.refresh_from_db()
        order.refresh_from_db()
        reservation = StockReservation.objects.get(order=order)

        self.assertEqual(order.status, "pending")
        self.assertEqual(payment.status, "unknown")
        self.assertNotEqual(payment.authority, "MOCK-EXPIRED-123")
        self.assertEqual(reservation.status, "active")
        recovered_gateway.inquire.assert_called_once()

    def test_unknown_gateway_result_blocks_new_payment_request(self):
        order = self.create_order(quantity=2)

        gateway = SimpleNamespace(
            request=Mock(
                return_value=PaymentResult(
                    success=False,
                    message="Gateway response is unknown.",
                    raw_response={
                        "step": "request",
                        "error": "connection_timeout",
                    },
                    outcome_unknown=True,
                )
            )
        )

        with patch("payments.views.get_gateway", return_value=gateway):
            first_response = self.initiate(order)

            self.assertEqual(first_response.status_code, 409)
            self.assertFalse(first_response.data["success"])

            payment = Payment.objects.get(order=order)

            self.assertEqual(payment.status, "unknown")
            self.assertIsNotNone(payment.request_started_at)
            self.assertEqual(
                payment.gateway_response["error"],
                "connection_timeout",
            )

            second_response = self.initiate(order)

        self.assertEqual(second_response.status_code, 409)
        self.assertEqual(gateway.request.call_count, 1)
        self.assertEqual(
            Payment.objects.filter(order=order).count(),
            1,
        )

    def test_mock_gateway_request_is_idempotent(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        gateway = get_gateway()
        request_key = str(payment.request_key)

        first_result = gateway.request(
            payment,
            request_key=request_key,
        )

        self.assertTrue(first_result.success)
        self.assertEqual(
            first_result.authority,
            payment.authority,
        )

        self.assertEqual(
            first_result.redirect_url,
            payment.gateway_response["redirect_url"],
        )

        self.assertEqual(
            first_result.authority,
            payment.gateway_response["authority"],
        )

        self.assertEqual(
            payment.gateway_response["request_key"],
            request_key,
        )

    def test_mock_gateway_request_recovers_existing_ledger_before_payment_response_is_saved(
        self,
    ):
        order = self.create_order(quantity=2)

        payment = Payment.objects.create(
            order=order,
            gateway="mock",
            amount=order.total_amount,
            status="initiating",
        )

        gateway = get_gateway()
        request_key = str(payment.request_key)

        first_result = gateway.request(
            payment,
            request_key=request_key,
        )

        second_result = gateway.request(
            payment,
            request_key=request_key,
        )

        self.assertTrue(first_result.success)
        self.assertTrue(second_result.success)
        self.assertEqual(
            second_result.authority,
            first_result.authority,
        )
        self.assertEqual(
            second_result.redirect_url,
            first_result.redirect_url,
        )
        self.assertEqual(
            MockGatewayTransaction.objects.filter(
                payment=payment,
            ).count(),
            1,
        )

    def test_mock_gateway_rejects_different_request_key(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        gateway = get_gateway()

        result = gateway.request(
            payment,
            request_key="different-request-key",
        )

        self.assertFalse(result.success)
        self.assertTrue(result.outcome_unknown)
        self.assertEqual(
            result.authority,
            None,
        )

        payment.refresh_from_db()

        self.assertEqual(
            payment.gateway_response["request_key"],
            str(payment.request_key),
        )

    def test_mock_gateway_request_rejects_different_key_from_existing_ledger(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        mock_transaction = MockGatewayTransaction.objects.get(
            payment=payment,
        )

        payment.gateway_response = {}
        payment.save(update_fields=["gateway_response"])

        gateway = get_gateway()
        result = gateway.request(
            payment,
            request_key="different-request-key",
        )

        self.assertFalse(result.success)
        self.assertTrue(result.outcome_unknown)
        self.assertEqual(
            result.raw_response["authority"],
            mock_transaction.authority,
        )

    def test_mock_gateway_transaction_inquiry_returns_unknown(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        gateway = get_gateway()
        result = gateway.inquire_transaction(payment)

        self.assertFalse(result.success)
        self.assertTrue(result.outcome_unknown)
        self.assertIsNone(result.ref_id)

        self.assertEqual(
            result.raw_response["step"],
            "request",
        )
        self.assertEqual(
            result.raw_response["authority"],
            payment.authority,
        )

    def test_mock_gateway_transaction_inquiry_without_transaction_returns_unknown(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        MockGatewayTransaction.objects.filter(payment=payment).delete()

        gateway = get_gateway()
        result = gateway.inquire_transaction(payment)

        self.assertFalse(result.success)
        self.assertTrue(result.outcome_unknown)
        self.assertIsNone(result.ref_id)
        self.assertEqual(
            result.raw_response["step"],
            "inquire_transaction",
        )
        self.assertEqual(
            result.raw_response["authority"],
            payment.authority,
        )

    def test_mock_gateway_transaction_inquiry_returns_success(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        transaction = MockGatewayTransaction.objects.get(payment=payment)
        transaction.status = "success"
        transaction.ref_id = "MOCK-REF-123"
        transaction.save(update_fields=["status", "ref_id"])

        gateway = get_gateway()
        result = gateway.inquire_transaction(payment)

        self.assertTrue(result.success)
        self.assertFalse(result.outcome_unknown)
        self.assertEqual(result.ref_id, "MOCK-REF-123")

    def test_mock_gateway_transaction_inquiry_returns_failure(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        transaction = MockGatewayTransaction.objects.get(payment=payment)
        transaction.status = "failed"
        transaction.save(update_fields=["status"])

        gateway = get_gateway()
        result = gateway.inquire_transaction(payment)

        self.assertFalse(result.success)
        self.assertFalse(result.outcome_unknown)
        self.assertIsNone(result.ref_id)

    def test_repeated_initiation_with_missing_redirect_url_returns_conflict(self):
        order = self.create_order(quantity=2)

        first_response = self.initiate(order)
        self.assertEqual(first_response.status_code, 200)

        payment = Payment.objects.get(pk=first_response.data["payment_id"])

        payment.gateway_response = {
            "step": "request",
            "authority": payment.authority,
        }
        payment.save(update_fields=["gateway_response"])

        second_response = self.initiate(order)

        self.assertEqual(second_response.status_code, 409)
        self.assertFalse(second_response.data["success"])

        payment.refresh_from_db()

        self.assertEqual(payment.status, "pending")
        self.assertTrue(payment.authority)
        self.assertEqual(
            Payment.objects.filter(order=order).count(),
            1,
        )

    def test_successful_payment_consumes_reservation_and_stock(self):
        order = self.create_order(quantity=2)
        reservation = StockReservation.objects.get(order=order)

        payment = self.start_payment(order)

        mock_request = RequestFactory().post(
            "/",
            {"status": "success"},
        )
        mock_response = mock_payment_page(
            mock_request,
            payment.id,
        )
        self.assertEqual(mock_response.status_code, 302)

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
        self.assertEqual(self.get_batch_physical_quantity(), 3)

    def test_gateway_success_after_reservation_expiry_keeps_payment_unknown(self):
        order = self.create_order(quantity=2)
        reservation = StockReservation.objects.get(order=order)
        payment = self.start_payment(order)

        # The mock gateway records a successful transaction while the
        # reservation is still valid.
        mock_request = RequestFactory().post(
            "/",
            {"status": "success"},
        )
        mock_response = mock_payment_page(
            mock_request,
            payment.id,
        )
        self.assertEqual(mock_response.status_code, 302)

        # The reservation expires before the verification callback arrives.
        expired_at = timezone.now() - timedelta(minutes=1)
        Order.objects.filter(pk=order.pk).update(reservation_expires_at=expired_at)
        StockReservation.objects.filter(order=order).update(expires_at=expired_at)

        response = self.verify(order, payment.authority)

        self.assertEqual(response.status_code, 409)

        order.refresh_from_db()
        payment.refresh_from_db()
        reservation.refresh_from_db()

        self.assertEqual(order.status, "cancelled")
        self.assertEqual(payment.status, "unknown")
        self.assertEqual(
            payment.gateway_response["reason"],
            "order_or_reservation_no_longer_valid",
        )
        self.assertEqual(reservation.status, "expired")
        self.assertIsNotNone(reservation.released_at)

        mock_transaction = MockGatewayTransaction.objects.get(payment=payment)
        self.assertEqual(mock_transaction.status, "success")

        self.assertEqual(self.get_batch_physical_quantity(), 5)
        self.assertFalse(InventoryDocument.objects.filter(source_order=order).exists())

    def test_expiry_command_does_not_release_reservation_during_verification(
        self,
    ):
        order = self.create_order(quantity=2)
        reservation = StockReservation.objects.get(order=order)
        payment = self.start_payment(order)

        expired_at = timezone.now() - timedelta(minutes=1)
        Order.objects.filter(pk=order.pk).update(reservation_expires_at=expired_at)
        StockReservation.objects.filter(order=order).update(expires_at=expired_at)

        gateway = get_gateway()
        gateway.verify = Mock(
            side_effect=lambda *args, **kwargs: self._run_expiry_during_verification(
                payment,
            )
        )
        with patch("payments.views.get_gateway", return_value=gateway):
            response = self.verify(order, payment.authority)

        self.assertEqual(response.status_code, 409)
        order.refresh_from_db()
        payment.refresh_from_db()
        reservation.refresh_from_db()

        self.assertEqual(order.status, "cancelled")
        self.assertEqual(payment.status, "unknown")
        self.assertEqual(reservation.status, "expired")
        self.assertIsNotNone(reservation.released_at)
        self.assertEqual(self.get_batch_physical_quantity(), 5)
        self.assertFalse(InventoryDocument.objects.filter(source_order=order).exists())

    def _run_expiry_during_verification(self, payment):
        call_command("expire_orders", stdout=StringIO())
        payment.refresh_from_db()
        self.assertEqual(payment.status, "verifying")
        return PaymentResult(
            success=True,
            ref_id="RACE-VERIFY-REF",
            raw_response={"status": "success"},
        )

    def test_successful_gateway_payment_with_insufficient_inventory_marks_payment_unknown(
        self,
    ):
        order = self.create_order(quantity=2)
        reservation = StockReservation.objects.get(order=order)
        payment = self.start_payment(order)

        document = InventoryDocument.objects.create(
            document_number="PAYMENT-TEST-OUT-001",
            document_type="outbound",
            created_by=self.user,
        )

        item = InventoryDocumentItem.objects.create(
            document=document,
            variant=self.variant,
            batch=self.batch,
            quantity=5,
            direction="outbound",
        )

        InventoryMovement.objects.create(
            batch=self.batch,
            document=document,
            document_item=item,
            movement_type="outbound",
            quantity_delta=-5,
            created_by=self.user,
        )

        self.assertEqual(self.get_batch_physical_quantity(), 0)

        mock_request = RequestFactory().post(
            "/",
            {"status": "success"},
        )
        mock_response = mock_payment_page(
            mock_request,
            payment.id,
        )
        self.assertEqual(mock_response.status_code, 302)

        response = self.verify(order, payment.authority)

        self.assertEqual(response.status_code, 409)

        order.refresh_from_db()
        payment.refresh_from_db()
        reservation.refresh_from_db()

        self.assertEqual(payment.status, "unknown")
        self.assertEqual(
            payment.gateway_response["reason"],
            "inventory_sale_failed",
        )
        self.assertEqual(order.status, "pending")
        self.assertEqual(reservation.status, "active")
        self.assertIsNone(reservation.consumed_at)
        self.assertEqual(self.get_batch_physical_quantity(), 0)
        self.assertFalse(InventoryDocument.objects.filter(source_order=order).exists())

    def test_recover_unknown_verification_completes_successful_payment(self):
        order = self.create_order(quantity=2)
        reservation = StockReservation.objects.get(order=order)
        payment = self.start_payment(order)

        mock_request = RequestFactory().post(
            "/",
            {"status": "success"},
        )
        mock_response = mock_payment_page(
            mock_request,
            payment.id,
        )
        self.assertEqual(mock_response.status_code, 302)

        payment.refresh_from_db()
        payment.status = "unknown"
        payment.verification_started_at = timezone.now() - timedelta(minutes=3)
        payment.gateway_response = {
            "step": "verify",
            "error": "connection_timeout",
            "outcome_unknown": True,
        }
        payment.save(
            update_fields=[
                "status",
                "verification_started_at",
                "gateway_response",
            ]
        )

        response = self.recover(order)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

        payment.refresh_from_db()
        order.refresh_from_db()
        reservation.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(payment.status, "success")
        self.assertTrue(payment.ref_id)
        self.assertEqual(order.status, "paid")
        self.assertEqual(reservation.status, "consumed")
        self.assertEqual(self.get_batch_physical_quantity(), 3)
        self.assertEqual(
            Payment.objects.filter(order=order).count(),
            1,
        )

    def test_recover_success_without_ref_id_keeps_payment_unknown(self):
        order = self.create_order(quantity=2)
        reservation = StockReservation.objects.get(order=order)
        payment = self.start_payment(order)

        mock_request = RequestFactory().post(
            "/",
            {"status": "success"},
        )
        mock_response = mock_payment_page(
            mock_request,
            payment.id,
        )
        self.assertEqual(mock_response.status_code, 302)

        mock_transaction = MockGatewayTransaction.objects.get(
            payment=payment,
        )
        mock_transaction.ref_id = ""
        mock_transaction.raw_response = {
            "step": "mock_payment",
            "status": "success",
            "authority": mock_transaction.authority,
            "ref_id": "",
        }
        mock_transaction.save(
            update_fields=["ref_id", "raw_response", "updated_at"],
        )

        payment.refresh_from_db()
        payment.status = "unknown"
        payment.verification_started_at = timezone.now() - timedelta(minutes=3)
        payment.gateway_response = {
            "step": "verify",
            "error": "connection_timeout",
            "outcome_unknown": True,
        }
        payment.save(
            update_fields=[
                "status",
                "verification_started_at",
                "gateway_response",
            ]
        )

        response = self.recover(order)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"], "missing_ref_id")

        payment.refresh_from_db()
        order.refresh_from_db()
        reservation.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(payment.status, "unknown")
        self.assertEqual(
            payment.gateway_response["error"],
            "missing_ref_id",
        )
        self.assertTrue(payment.gateway_response["outcome_unknown"])
        self.assertEqual(order.status, "pending")
        self.assertEqual(reservation.status, "active")
        self.assertEqual(self.get_batch_physical_quantity(), 5)

    def test_recover_definitive_verification_failure_returns_400(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        mock_request = RequestFactory().post(
            "/",
            {"status": "cancelled"},
        )
        mock_response = mock_payment_page(
            mock_request,
            payment.id,
        )
        self.assertEqual(mock_response.status_code, 302)

        payment.refresh_from_db()
        payment.status = "unknown"
        payment.verification_started_at = timezone.now() - timedelta(minutes=3)
        payment.gateway_response = {
            "step": "verify",
            "error": "connection_timeout",
            "outcome_unknown": True,
        }
        payment.save(
            update_fields=[
                "status",
                "verification_started_at",
                "gateway_response",
            ]
        )

        response = self.recover(order)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["success"], False)

        payment.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(payment.status, "failed")
        self.assertEqual(order.status, "pending")

    def test_recover_successful_verification_with_amount_mismatch_stays_unknown(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        mock_request = RequestFactory().post(
            "/",
            {"status": "success"},
        )
        mock_response = mock_payment_page(
            mock_request,
            payment.id,
        )
        self.assertEqual(mock_response.status_code, 302)

        payment.refresh_from_db()
        payment.amount += 1000
        payment.status = "unknown"
        payment.verification_started_at = timezone.now() - timedelta(minutes=3)
        payment.gateway_response = {
            "step": "verify",
            "error": "connection_timeout",
            "outcome_unknown": True,
        }
        payment.save(
            update_fields=[
                "amount",
                "status",
                "verification_started_at",
                "gateway_response",
            ]
        )

        response = self.recover(order)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data["error"],
            "payment_amount_mismatch",
        )

        payment.refresh_from_db()
        order.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(payment.status, "unknown")
        self.assertEqual(
            payment.gateway_response["reason"],
            "payment_amount_mismatch",
        )
        self.assertEqual(order.status, "pending")
        self.assertEqual(self.get_batch_physical_quantity(), 5)

    def test_repeated_callback_does_not_decrease_stock_twice(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        mock_request = RequestFactory().post(
            "/",
            {"status": "success"},
        )
        mock_response = mock_payment_page(
            mock_request,
            payment.id,
        )
        self.assertEqual(mock_response.status_code, 302)

        first_response = self.verify(order, payment.authority)

        self.assertEqual(first_response.status_code, 200)
        self.assertTrue(first_response.data["success"])

        second_response = self.verify(order, payment.authority)

        self.assertEqual(second_response.status_code, 200)
        self.assertTrue(second_response.data["already_paid"])

        self.variant.refresh_from_db()

        self.assertEqual(self.get_batch_physical_quantity(), 3)
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

        mock_request = RequestFactory().post(
            "/",
            {"status": "cancelled"},
        )
        mock_response = mock_payment_page(
            mock_request,
            first_payment.id,
        )
        self.assertEqual(mock_response.status_code, 302)

        response = self.verify(
            order,
            first_payment.authority,
            status="failed",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])

        first_payment.refresh_from_db()
        reservation.refresh_from_db()

        self.assertEqual(first_payment.status, "failed")
        self.assertEqual(reservation.status, "active")

        self.variant.refresh_from_db()
        self.assertEqual(self.get_batch_physical_quantity(), 5)

        second_payment = self.start_payment(order)

        self.assertNotEqual(first_payment.id, second_payment.id)

        mock_request = RequestFactory().post(
            "/",
            {"status": "success"},
        )
        mock_response = mock_payment_page(
            mock_request,
            second_payment.id,
        )
        self.assertEqual(mock_response.status_code, 302)

        success_response = self.verify(
            order,
            second_payment.authority,
        )

        self.assertEqual(success_response.status_code, 200)
        self.assertTrue(success_response.data["success"])

        order.refresh_from_db()
        self.variant.refresh_from_db()

        self.assertEqual(order.status, "paid")
        self.assertEqual(self.get_batch_physical_quantity(), 3)

    def test_expired_reservation_cannot_be_paid(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        expired_at = timezone.now() - timedelta(minutes=1)

        Order.objects.filter(pk=order.pk).update(reservation_expires_at=expired_at)

        StockReservation.objects.filter(order=order).update(expires_at=expired_at)
        mock_request = RequestFactory().post(
            "/",
            {"status": "success"},
        )
        mock_response = mock_payment_page(
            mock_request,
            payment.id,
        )
        self.assertEqual(mock_response.status_code, 200)

        mock_transaction = MockGatewayTransaction.objects.get(payment=payment)
        self.assertEqual(mock_transaction.status, "failed")
        response = self.verify(order, payment.authority)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"], "این سفارش قابل تأیید نیست.")

        order.refresh_from_db()
        payment.refresh_from_db()

        reservation = StockReservation.objects.get(order=order)

        self.assertEqual(order.status, "cancelled")
        self.assertEqual(payment.status, "failed")
        self.assertEqual(reservation.status, "expired")
        self.assertIsNotNone(reservation.released_at)

        self.variant.refresh_from_db()
        self.assertEqual(self.get_batch_physical_quantity(), 5)

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
        self.assertEqual(self.get_batch_physical_quantity(), 5)

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
        self.assertEqual(self.get_batch_physical_quantity(), 5)

    def test_other_user_cannot_initiate_payment(self):
        order = self.create_order(quantity=2)

        other_user = User.objects.create_user(
            username="other-payment-user",
            password="test-password",
        )
        self.client.force_authenticate(user=other_user)

        response = self.initiate(order)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Payment.objects.filter(order=order).count(), 0)

    def test_other_user_cannot_verify_payment(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        other_user = User.objects.create_user(
            username="other-verify-user",
            password="test-password",
        )
        self.client.force_authenticate(user=other_user)

        response = self.verify(order, payment.authority)

        self.assertEqual(response.status_code, 404)

        order.refresh_from_db()
        payment.refresh_from_db()
        self.variant.refresh_from_db()

        reservation = StockReservation.objects.get(order=order)

        self.assertEqual(order.status, "pending")
        self.assertEqual(payment.status, "pending")
        self.assertEqual(reservation.status, "active")
        self.assertEqual(self.get_batch_physical_quantity(), 5)

    def test_mock_payment_page_displays_pending_transaction(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)
        response = self.client.get(f"/api/payments/mock/{payment.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/mock_payment.html")

    def test_mock_payment_page_hides_expired_reservation_without_mutation(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        expired_at = timezone.now() - timedelta(minutes=1)

        Order.objects.filter(pk=order.pk).update(
            reservation_expires_at=expired_at,
        )
        StockReservation.objects.filter(order=order).update(
            expires_at=expired_at,
        )

        response = self.client.get(f"/api/payments/mock/{payment.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            "payments/mock_already_processed.html",
        )

        order.refresh_from_db()
        payment.refresh_from_db()
        mock_transaction = MockGatewayTransaction.objects.get(payment=payment)
        reservation = StockReservation.objects.get(order=order)

        self.assertEqual(order.status, "pending")
        self.assertEqual(payment.status, "pending")
        self.assertEqual(mock_transaction.status, "pending")
        self.assertEqual(reservation.status, "active")
        self.assertIsNone(reservation.released_at)

    def test_mock_payment_page_returns_404_without_mock_transaction(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        MockGatewayTransaction.objects.filter(payment=payment).delete()

        response = self.client.get(f"/api/payments/mock/{payment.id}/")

        self.assertEqual(response.status_code, 404)

    def test_mock_payment_page_records_success_transaction(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        request = RequestFactory().post(
            "/",
            {"status": "success"},
        )

        response = mock_payment_page(request, payment.id)

        self.assertEqual(response.status_code, 302)

        mock_transaction = MockGatewayTransaction.objects.get(
            payment=payment,
        )

        self.assertEqual(mock_transaction.status, "success")
        self.assertTrue(mock_transaction.ref_id)
        self.assertTrue(mock_transaction.ref_id.startswith("MOCK-REF-"))
        self.assertEqual(
            mock_transaction.raw_response["submitted_status"],
            "success",
        )

    def test_mock_payment_page_records_cancelled_transaction(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        request = RequestFactory().post(
            "/",
            {"status": "cancelled"},
        )

        response = mock_payment_page(request, payment.id)

        self.assertEqual(response.status_code, 302)

        mock_transaction = MockGatewayTransaction.objects.get(
            payment=payment,
        )

        self.assertEqual(mock_transaction.status, "failed")
        self.assertEqual(mock_transaction.ref_id, "")
        self.assertEqual(
            mock_transaction.raw_response["submitted_status"],
            "cancelled",
        )

    def test_mock_payment_page_rejects_invalid_status(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        request = RequestFactory().post(
            "/",
            {"status": "invalid"},
        )

        response = mock_payment_page(request, payment.id)

        self.assertEqual(response.status_code, 400)

        mock_transaction = MockGatewayTransaction.objects.get(
            payment=payment,
        )

        self.assertEqual(mock_transaction.status, "pending")
        self.assertEqual(mock_transaction.ref_id, "")

    def test_mock_payment_page_does_not_overwrite_processed_transaction(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        success_request = RequestFactory().post(
            "/",
            {"status": "success"},
        )
        first_response = mock_payment_page(
            success_request,
            payment.id,
        )

        self.assertEqual(first_response.status_code, 302)

        mock_transaction = MockGatewayTransaction.objects.get(
            payment=payment,
        )
        original_ref_id = mock_transaction.ref_id

        cancelled_request = RequestFactory().post(
            "/",
            {"status": "cancelled"},
        )
        second_response = mock_payment_page(
            cancelled_request,
            payment.id,
        )

        self.assertEqual(second_response.status_code, 200)

        mock_transaction.refresh_from_db()

        self.assertEqual(mock_transaction.status, "success")
        self.assertEqual(mock_transaction.ref_id, original_ref_id)

    def test_mock_payment_page_rejects_unsupported_http_method(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        request = RequestFactory().put("/")

        response = mock_payment_page(request, payment.id)

        self.assertEqual(response.status_code, 405)

        mock_transaction = MockGatewayTransaction.objects.get(
            payment=payment,
        )
        self.assertEqual(mock_transaction.status, "pending")

    def test_mock_payment_page_url_rejects_unsupported_http_method(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        response = self.client.put(
            f"/api/payments/mock/{payment.id}/",
        )

        self.assertEqual(response.status_code, 405)

        mock_transaction = MockGatewayTransaction.objects.get(
            payment=payment,
        )
        self.assertEqual(mock_transaction.status, "pending")

    def test_mock_success_without_ref_id_marks_payment_unknown(self):
        order = self.create_order(quantity=2)
        start_response = self.initiate(order)

        self.assertEqual(start_response.status_code, 200)

        payment = Payment.objects.get(order=order)

        mock_transaction = MockGatewayTransaction.objects.get(
            payment=payment,
        )

        mock_transaction.status = "success"
        mock_transaction.ref_id = ""
        mock_transaction.raw_response = {
            "step": "mock_payment",
            "status": "success",
            "authority": mock_transaction.authority,
            "ref_id": "",
        }
        mock_transaction.save(
            update_fields=[
                "status",
                "ref_id",
                "raw_response",
                "updated_at",
            ]
        )

        response = self.verify(
            order,
            payment.authority,
            status="success",
        )

        self.assertEqual(response.status_code, 409)

        payment.refresh_from_db()
        order.refresh_from_db()
        self.variant.refresh_from_db()

        reservation = StockReservation.objects.get(order=order)

        self.assertEqual(payment.status, "unknown")
        self.assertEqual(order.status, "pending")
        self.assertEqual(self.get_batch_physical_quantity(), 5)
        self.assertEqual(reservation.status, "active")
        self.assertEqual(
            payment.gateway_response["error"],
            "missing_ref_id",
        )

    @override_settings(DEBUG=False, ACTIVE_PAYMENT_GATEWAY="mock")
    def test_mock_gateway_is_disabled_in_production(self):
        with self.assertRaises(ImproperlyConfigured):
            get_gateway()

    def test_recover_pending_payment_returns_conflict(self):
        order = self.create_order(quantity=2)
        payment = self.start_payment(order)

        self.assertEqual(payment.status, "pending")

        response = self.recover(order)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["success"], False)

        payment.refresh_from_db()
        self.assertEqual(payment.status, "pending")

    @override_settings(DEBUG=False, ACTIVE_PAYMENT_GATEWAY="mock")
    def test_mock_payment_page_is_hidden_in_production(self):
        request = RequestFactory().get("/")

        with self.assertRaises(Http404):
            mock_payment_page(request, payment_id=1)


@override_settings(DEBUG=True, ACTIVE_PAYMENT_GATEWAY="mock")
class PaymentTransactionBoundaryTests(TransactionTestCase):
    def test_gateway_request_runs_outside_atomic_transaction(self):
        user = User.objects.create_user(
            username="transaction-test-user",
            password="test-password",
        )

        brand = Brand.objects.create(
            name="Transaction Brand",
            slug="transaction-brand",
        )

        category = Category.objects.create(
            name="Transaction Category",
            slug="transaction-category",
        )

        product = Product.objects.create(
            name_fa="محصول تست تراکنش",
            slug="transaction-test-product",
            brand=brand,
            category=category,
            description="Transaction test",
        )

        variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=5,
            shipping_weight_grams=1000,
        )
        create_inventory_ledger_for_variant(variant, user)
        shipping_method = ShippingMethod.objects.create(
            name="ارسال تست تراکنش",
            slug="transaction-test-shipping",
        )

        ShippingRate.objects.create(
            method=shipping_method,
            province="tehran",
            cost=Decimal("50000"),
        )

        serializer = CreateOrderSerializer(
            data=attach_checkout_quote({
                "items": [
                    {
                        "variant_id": variant.id,
                        "quantity": 2,
                    }
                ],
                "shipping_method_slug": "transaction-test-shipping",
                "province": "tehran",
                "city_code": get_test_tehran_city().code,
                "address": "آدرس معتبر آزمایشی",
                "postal_code": "1234567890",
                "first_name": "Test",
                "last_name": "User",
                "mobile": "09123456789",
                "notes": "",
            }, user),
            context={"request": SimpleNamespace(user=user)},
        )

        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        client = APIClient()
        client.force_authenticate(user=user)

        observed_atomic_state = []

        def fake_request(payment, request_key):
            observed_atomic_state.append(connection.in_atomic_block)

            return PaymentResult(
                success=True,
                authority="TEST-AUTHORITY",
                redirect_url="https://example.com/pay",
                raw_response={
                    "step": "request",
                    "authority": "TEST-AUTHORITY",
                    "redirect_url": "https://example.com/pay",
                    "request_key": request_key,
                },
            )

        gateway = SimpleNamespace(request=fake_request)

        with patch("payments.views.get_gateway", return_value=gateway):
            response = client.post(
                "/api/payments/initiate/",
                {"order_number": order.order_number},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(observed_atomic_state, [False])

        payment = Payment.objects.get(order=order)
        self.assertEqual(payment.status, "pending")

    def test_gateway_verify_runs_outside_atomic_transaction(self):
        user = User.objects.create_user(
            username="verify-transaction-user",
            password="test-password",
        )

        brand = Brand.objects.create(
            name="Verify Transaction Brand",
            slug="verify-transaction-brand",
        )

        category = Category.objects.create(
            name="Verify Transaction Category",
            slug="verify-transaction-category",
        )

        product = Product.objects.create(
            name_fa="محصول تست تأیید تراکنش",
            slug="verify-transaction-product",
            brand=brand,
            category=category,
            description="Verify transaction test",
        )

        variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=5,
            shipping_weight_grams=1000,
        )
        create_inventory_ledger_for_variant(variant, user)

        shipping_method = ShippingMethod.objects.create(
            name="ارسال تست تأیید تراکنش",
            slug="verify-transaction-shipping",
        )

        ShippingRate.objects.create(
            method=shipping_method,
            province="tehran",
            cost=Decimal("50000"),
        )

        serializer = CreateOrderSerializer(
            data=attach_checkout_quote({
                "items": [
                    {
                        "variant_id": variant.id,
                        "quantity": 2,
                    }
                ],
                "shipping_method_slug": "verify-transaction-shipping",
                "province": "tehran",
                "city_code": get_test_tehran_city().code,
                "address": "آدرس معتبر آزمایشی",
                "postal_code": "1234567890",
                "first_name": "Test",
                "last_name": "User",
                "mobile": "09123456789",
                "notes": "",
            }, user),
            context={"request": SimpleNamespace(user=user)},
        )

        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        client = APIClient()
        client.force_authenticate(user=user)

        payment = Payment.objects.create(
            order=order,
            gateway="mock",
            amount=order.total_amount,
            status="pending",
            authority="VERIFY-TEST-AUTHORITY",
        )

        observed_atomic_state = []
        second_callback_responses = []
        verify_call_count = []

        def fake_verify(payment, params=None):
            observed_atomic_state.append(connection.in_atomic_block)
            verify_call_count.append(1)

            second_response = client.post(
                "/api/payments/verify/",
                {
                    "order_number": order.order_number,
                    "authority": payment.authority,
                    "status": "success",
                },
                format="json",
            )

            second_callback_responses.append(second_response)

            return PaymentResult(
                success=True,
                ref_id="VERIFY-TEST-REF",
                raw_response={
                    "step": "verify",
                    "status": "success",
                    "ref_id": "VERIFY-TEST-REF",
                },
            )

        gateway = SimpleNamespace(verify=fake_verify)

        with patch("payments.views.get_gateway", return_value=gateway):
            response = client.post(
                "/api/payments/verify/",
                {
                    "order_number": order.order_number,
                    "authority": payment.authority,
                    "status": "success",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(second_callback_responses[0].status_code, 409)
        self.assertEqual(observed_atomic_state, [False])

    def test_verify_rejects_concurrent_request_while_first_is_verifying(self):
        user = User.objects.create_user(
            username="verify-concurrency-user",
            password="test-password",
        )

        brand = Brand.objects.create(
            name="Verify Concurrency Brand",
            slug="verify-concurrency-brand",
        )

        category = Category.objects.create(
            name="Verify Concurrency Category",
            slug="verify-concurrency-category",
        )

        product = Product.objects.create(
            name_fa="محصول تست هم‌زمانی تأیید",
            slug="verify-concurrency-product",
            brand=brand,
            category=category,
            description="Verify concurrency test",
        )

        variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=5,
            shipping_weight_grams=1000,
        )
        create_inventory_ledger_for_variant(variant, user)
        shipping_method = ShippingMethod.objects.create(
            name="ارسال تست هم‌زمانی تأیید",
            slug="verify-concurrency-shipping",
        )

        ShippingRate.objects.create(
            method=shipping_method,
            province="tehran",
            cost=Decimal("50000"),
        )

        serializer = CreateOrderSerializer(
            data=attach_checkout_quote({
                "items": [{"variant_id": variant.id, "quantity": 2}],
                "shipping_method_slug": "verify-concurrency-shipping",
                "province": "tehran",
                "city_code": get_test_tehran_city().code,
                "address": "آدرس معتبر آزمایشی",
                "postal_code": "1234567890",
                "first_name": "Test",
                "last_name": "User",
                "mobile": "09123456789",
                "notes": "",
            }, user),
            context={"request": SimpleNamespace(user=user)},
        )

        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        payment = Payment.objects.create(
            order=order,
            gateway="mock",
            amount=order.total_amount,
            status="pending",
            authority="VERIFY-CONCURRENCY-AUTHORITY",
        )

        gateway_started = Event()
        allow_gateway_finish = Event()
        verify_call_count = []

        def fake_verify(payment, params=None):
            verify_call_count.append(1)
            gateway_started.set()

            if not allow_gateway_finish.wait(timeout=15):
                raise TimeoutError("Gateway test wait timed out")

            return PaymentResult(
                success=True,
                ref_id="VERIFY-CONCURRENCY-REF",
                raw_response={
                    "step": "verify",
                    "status": "success",
                    "ref_id": "VERIFY-CONCURRENCY-REF",
                },
            )

        gateway = SimpleNamespace(verify=fake_verify)

        def send_verify_request():
            close_old_connections()
            try:
                request_user = User.objects.get(pk=user.pk)
                client = APIClient()
                client.force_authenticate(user=request_user)

                return client.post(
                    "/api/payments/verify/",
                    {
                        "order_number": order.order_number,
                        "authority": payment.authority,
                        "status": "success",
                    },
                    format="json",
                )
            finally:
                close_old_connections()

        with patch("payments.views.get_gateway", return_value=gateway):
            with ThreadPoolExecutor(max_workers=2) as executor:
                first_future = executor.submit(send_verify_request)

                try:
                    self.assertTrue(
                        gateway_started.wait(timeout=10),
                        "First verification did not reach the gateway",
                    )

                    second_future = executor.submit(send_verify_request)
                    second_response = second_future.result(timeout=10)
                finally:
                    allow_gateway_finish.set()

                first_response = first_future.result(timeout=15)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 409)
        self.assertEqual(verify_call_count, [1])

        payment.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(payment.status, "success")
        self.assertEqual(payment.ref_id, "VERIFY-CONCURRENCY-REF")
        self.assertEqual(order.status, "paid")

    def test_recover_rejects_concurrent_request_while_first_is_inquiring(self):
        user = User.objects.create_user(
            username="recover-concurrency-user",
            password="test-password",
        )

        brand = Brand.objects.create(
            name="Recover Concurrency Brand",
            slug="recover-concurrency-brand",
        )

        category = Category.objects.create(
            name="Recover Concurrency Category",
            slug="recover-concurrency-category",
        )

        product = Product.objects.create(
            name_fa="محصول تست هم‌زمانی بازیابی",
            slug="recover-concurrency-product",
            brand=brand,
            category=category,
            description="Recover concurrency test",
        )

        variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=5,
            shipping_weight_grams=1000,
        )
        create_inventory_ledger_for_variant(variant, user)

        shipping_method = ShippingMethod.objects.create(
            name="ارسال تست هم‌زمانی بازیابی",
            slug="recover-concurrency-shipping",
        )

        ShippingRate.objects.create(
            method=shipping_method,
            province="tehran",
            cost=Decimal("50000"),
        )

        serializer = CreateOrderSerializer(
            data=attach_checkout_quote({
                "items": [{"variant_id": variant.id, "quantity": 2}],
                "shipping_method_slug": "recover-concurrency-shipping",
                "province": "tehran",
                "city_code": get_test_tehran_city().code,
                "address": "آدرس معتبر آزمایشی",
                "postal_code": "1234567890",
                "first_name": "Test",
                "last_name": "User",
                "mobile": "09123456789",
                "notes": "",
            }, user),
            context={"request": SimpleNamespace(user=user)},
        )

        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        payment = Payment.objects.create(
            order=order,
            gateway="mock",
            amount=order.total_amount,
            status="unknown",
            request_key="7aefb1c0-5c5d-4e9d-9b13-1c6e9c1a4a01",
            request_started_at=timezone.now() - timedelta(minutes=3),
            gateway_response={
                "step": "request",
                "error": "gateway_exception",
                "outcome_unknown": True,
            },
        )

        gateway_started = Event()
        allow_gateway_finish = Event()
        inquiry_call_count = []

        def fake_inquire(payment, request_key):
            inquiry_call_count.append(1)
            gateway_started.set()

            if not allow_gateway_finish.wait(timeout=15):
                raise TimeoutError("Gateway inquiry test wait timed out")

            return PaymentResult(
                success=True,
                authority="RECOVER-CONCURRENCY-AUTHORITY",
                redirect_url="https://example.test/payment",
                raw_response={
                    "step": "request",
                    "status": "success",
                    "authority": "RECOVER-CONCURRENCY-AUTHORITY",
                },
            )

        gateway = SimpleNamespace(inquire=fake_inquire)

        def send_recovery_request():
            close_old_connections()
            try:
                request_user = User.objects.get(pk=user.pk)
                client = APIClient()
                client.force_authenticate(user=request_user)

                return client.post(
                    "/api/payments/recover/",
                    {"order_number": order.order_number},
                    format="json",
                )
            finally:
                close_old_connections()

        with patch("payments.views.get_gateway", return_value=gateway):
            with ThreadPoolExecutor(max_workers=2) as executor:
                first_future = executor.submit(send_recovery_request)

                try:
                    self.assertTrue(
                        gateway_started.wait(timeout=10),
                        "First recovery did not reach the gateway",
                    )

                    second_future = executor.submit(send_recovery_request)
                    second_response = second_future.result(timeout=10)
                finally:
                    allow_gateway_finish.set()

                first_response = first_future.result(timeout=15)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 409)
        self.assertEqual(inquiry_call_count, [1])

        payment.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(payment.status, "pending")
        self.assertEqual(
            payment.authority,
            "RECOVER-CONCURRENCY-AUTHORITY",
        )
        self.assertEqual(order.status, "pending")

    def test_gateway_verify_exception_marks_payment_unknown(self):
        user = User.objects.create_user(
            username="verify-exception-user",
            password="test-password",
        )

        brand = Brand.objects.create(
            name="Verify Exception Brand",
            slug="verify-exception-brand",
        )

        category = Category.objects.create(
            name="Verify Exception Category",
            slug="verify-exception-category",
        )

        product = Product.objects.create(
            name_fa="محصول تست خطای تأیید",
            slug="verify-exception-product",
            brand=brand,
            category=category,
            description="Verify exception test",
        )

        variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=5,
            shipping_weight_grams=1000,
        )
        create_inventory_ledger_for_variant(variant, user)

        shipping_method = ShippingMethod.objects.create(
            name="ارسال تست خطای تأیید",
            slug="verify-exception-shipping",
        )

        ShippingRate.objects.create(
            method=shipping_method,
            province="tehran",
            cost=Decimal("50000"),
        )

        serializer = CreateOrderSerializer(
            data=attach_checkout_quote({
                "items": [
                    {
                        "variant_id": variant.id,
                        "quantity": 2,
                    }
                ],
                "shipping_method_slug": "verify-exception-shipping",
                "province": "tehran",
                "city_code": get_test_tehran_city().code,
                "address": "آدرس معتبر آزمایشی",
                "postal_code": "1234567890",
                "first_name": "Test",
                "last_name": "User",
                "mobile": "09123456789",
                "notes": "",
            }, user),
            context={"request": SimpleNamespace(user=user)},
        )

        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        client = APIClient()
        client.force_authenticate(user=user)

        payment = Payment.objects.create(
            order=order,
            gateway="mock",
            amount=order.total_amount,
            status="pending",
            authority="VERIFY-EXCEPTION-AUTHORITY",
        )

        def fake_verify(payment, params=None):
            raise RuntimeError("Gateway connection failed")

        gateway = SimpleNamespace(verify=fake_verify)

        with patch("payments.views.get_gateway", return_value=gateway):
            response = client.post(
                "/api/payments/verify/",
                {
                    "order_number": order.order_number,
                    "authority": payment.authority,
                    "status": "success",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 409)

        payment.refresh_from_db()
        order.refresh_from_db()

        self.assertEqual(payment.status, "unknown")
        self.assertEqual(
            payment.gateway_response["error"],
            "gateway_exception",
        )
        self.assertEqual(order.status, "pending")

    def test_mock_gateway_request_is_safe_under_concurrent_calls(self):
        user = User.objects.create_user(
            username="concurrent-request-user",
            password="test-password",
        )

        brand = Brand.objects.create(
            name="Concurrent Brand",
            slug="concurrent-brand",
        )

        category = Category.objects.create(
            name="Concurrent Category",
            slug="concurrent-category",
        )

        product = Product.objects.create(
            name_fa="Concurrent Test Product",
            slug="concurrent-test-product",
            brand=brand,
            category=category,
            description="Concurrent request test",
        )

        variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=5,
            shipping_weight_grams=1000,
        )
        create_inventory_ledger_for_variant(variant, user)

        shipping_method = ShippingMethod.objects.create(
            name="Concurrent Shipping",
            slug="concurrent-shipping",
        )

        ShippingRate.objects.create(
            method=shipping_method,
            province="tehran",
            cost=Decimal("50000"),
        )

        serializer = CreateOrderSerializer(
            data=attach_checkout_quote({
                "items": [
                    {
                        "variant_id": variant.id,
                        "quantity": 2,
                    }
                ],
                "shipping_method_slug": "concurrent-shipping",
                "province": "tehran",
                "city_code": get_test_tehran_city().code,
                "address": "Concurrent test address",
                "postal_code": "1234567890",
                "first_name": "Test",
                "last_name": "User",
                "mobile": "09123456789",
                "notes": "",
            }, user),
            context={"request": SimpleNamespace(user=user)},
        )

        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        payment = Payment.objects.create(
            order=order,
            gateway="mock",
            amount=order.total_amount,
            status="initiating",
        )

        payment_id = payment.pk
        request_key = str(payment.request_key)
        barrier = Barrier(2)

        def make_request():
            close_old_connections()

            try:
                barrier.wait(timeout=10)

                payment_obj = Payment.objects.get(pk=payment_id)

                result = get_gateway().request(
                    payment_obj,
                    request_key=request_key,
                )

                return (
                    result.success,
                    result.authority,
                    result.redirect_url,
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(make_request),
                executor.submit(make_request),
            ]

            results = [future.result(timeout=30) for future in futures]

        self.assertTrue(all(result[0] for result in results))
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(results[0][2], results[1][2])

        self.assertEqual(
            MockGatewayTransaction.objects.filter(
                payment_id=payment_id,
            ).count(),
            1,
        )

    def test_initiate_payment_is_safe_under_concurrent_requests(self):
        user = User.objects.create_user(
            username="concurrent-initiate-user",
            password="test-password",
        )

        brand = Brand.objects.create(
            name="Concurrent Initiate Brand",
            slug="concurrent-initiate-brand",
        )

        category = Category.objects.create(
            name="Concurrent Initiate Category",
            slug="concurrent-initiate-category",
        )

        product = Product.objects.create(
            name_fa="Concurrent Initiate Product",
            slug="concurrent-initiate-product",
            brand=brand,
            category=category,
            description="Concurrent initiate test",
        )

        variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=5,
            shipping_weight_grams=1000,
        )
        create_inventory_ledger_for_variant(variant, user)

        shipping_method = ShippingMethod.objects.create(
            name="Concurrent Initiate Shipping",
            slug="concurrent-initiate-shipping",
        )

        ShippingRate.objects.create(
            method=shipping_method,
            province="tehran",
            cost=Decimal("50000"),
        )

        serializer = CreateOrderSerializer(
            data=attach_checkout_quote({
                "items": [
                    {
                        "variant_id": variant.id,
                        "quantity": 2,
                    }
                ],
                "shipping_method_slug": "concurrent-initiate-shipping",
                "province": "tehran",
                "city_code": get_test_tehran_city().code,
                "address": "Concurrent initiate test address",
                "postal_code": "1234567890",
                "first_name": "Test",
                "last_name": "User",
                "mobile": "09123456789",
                "notes": "",
            }, user),
            context={"request": SimpleNamespace(user=user)},
        )

        serializer.is_valid(raise_exception=True)
        order = serializer.save()

        user_id = user.pk
        order_number = order.order_number
        barrier = Barrier(2)

        def initiate():
            close_old_connections()

            try:
                client = APIClient()
                thread_user = User.objects.get(pk=user_id)
                client.force_authenticate(user=thread_user)

                barrier.wait(timeout=10)

                response = client.post(
                    "/api/payments/initiate/",
                    {"order_number": order_number},
                    format="json",
                )

                return (
                    response.status_code,
                    response.data.get("payment_id"),
                )
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(initiate),
                executor.submit(initiate),
            ]

            results = [future.result(timeout=30) for future in futures]

        self.assertTrue(all(status in (200, 409) for status, _ in results))

        payment_ids = {
            payment_id for status, payment_id in results if payment_id is not None
        }

        self.assertEqual(len(payment_ids), 1)

        self.assertEqual(
            Payment.objects.filter(order=order).count(),
            1,
        )
