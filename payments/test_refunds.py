from decimal import Decimal
from uuid import uuid4

from django.contrib.auth.models import User
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from orders.models import Order, ReturnRequest
from payments.models import Payment, Refund
from payments.refund_services import RefundError, create_refund, transition_refund


class RefundWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("refund-customer")
        self.staff = User.objects.create_user("refund-staff")
        self.order = Order.objects.create(
            user=self.user, first_name="Test", last_name="Customer",
            mobile="09123456789", province="tehran", city="Tehran",
            address="Test address", subtotal=Decimal("100000"),
            vat_amount=Decimal("10000"), total_amount=Decimal("110000"),
            status="delivered",
        )
        self.payment = Payment.objects.create(
            order=self.order, gateway="mock", amount=Decimal("110000"),
            status="success", ref_id="CAPTURE-REF",
        )
        self.return_request = ReturnRequest.objects.create(
            order=self.order, user=self.user, reason="مرجوعی", status="received",
        )

    def test_refund_cannot_exceed_successful_payment(self):
        with self.assertRaises(RefundError):
            create_refund(
                return_request_id=self.return_request.pk,
                amount=Decimal("110001"), actor=self.staff, idempotency_key=uuid4(),
            )

    def test_refund_reserves_amount_against_duplicate_partial_refunds(self):
        create_refund(
            return_request_id=self.return_request.pk,
            amount=Decimal("70000"), actor=self.staff, idempotency_key=uuid4(),
        )
        with self.assertRaises(RefundError):
            create_refund(
                return_request_id=self.return_request.pk,
                amount=Decimal("50000"), actor=self.staff, idempotency_key=uuid4(),
            )

    def test_refund_requires_received_return(self):
        self.return_request.status = "approved"
        self.return_request.save(update_fields=["status"])
        with self.assertRaises(RefundError):
            create_refund(
                return_request_id=self.return_request.pk,
                amount=Decimal("1000"), actor=self.staff, idempotency_key=uuid4(),
            )

    def test_refund_idempotency_key_reuses_same_record(self):
        key = uuid4()
        first = create_refund(
            return_request_id=self.return_request.pk, amount=Decimal("10000"),
            actor=self.staff, idempotency_key=key,
        )
        second = create_refund(
            return_request_id=self.return_request.pk, amount=Decimal("10000"),
            actor=self.staff, idempotency_key=key,
        )
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Refund.objects.count(), 1)

    def test_refund_idempotency_key_cannot_be_reused_for_other_amount(self):
        key = uuid4()
        create_refund(
            return_request_id=self.return_request.pk, amount=Decimal("10000"),
            actor=self.staff, idempotency_key=key,
        )
        with self.assertRaises(RefundError):
            create_refund(
                return_request_id=self.return_request.pk, amount=Decimal("11000"),
                actor=self.staff, idempotency_key=key,
            )

    def test_refund_success_requires_provider_reference(self):
        refund = create_refund(
            return_request_id=self.return_request.pk,
            amount=Decimal("10000"), actor=self.staff, idempotency_key=uuid4(),
        )
        transition_refund(
            refund_id=refund.pk, actor=self.staff, decision="approve"
        )
        with self.assertRaises(RefundError):
            transition_refund(
                refund_id=refund.pk, actor=self.staff, decision="succeeded"
            )

    def test_refund_success_records_provider_reference_and_is_idempotent(self):
        refund = create_refund(
            return_request_id=self.return_request.pk,
            amount=Decimal("10000"), actor=self.staff, idempotency_key=uuid4(),
        )
        transition_refund(
            refund_id=refund.pk, actor=self.staff, decision="approve"
        )
        transition_refund(
            refund_id=refund.pk, actor=self.staff, decision="processing"
        )
        completed = transition_refund(
            refund_id=refund.pk, actor=self.staff, decision="succeeded",
            provider_reference="REFUND-123", provider_response={"status": "ok"},
        )
        repeated = transition_refund(
            refund_id=refund.pk, actor=self.staff, decision="succeeded",
            provider_reference="REFUND-123",
        )
        self.assertEqual(completed.pk, repeated.pk)
        self.assertEqual(repeated.status, "succeeded")
        self.assertEqual(repeated.provider_reference, "REFUND-123")
        self.assertEqual(list(repeated.history.values_list("new_status", flat=True)), ["requested", "approved", "processing", "succeeded"])
        self.return_request.refresh_from_db()
        self.assertEqual(self.return_request.status, "closed")
        self.assertEqual(list(self.return_request.history.values_list("new_status", flat=True)), ["closed"])



class RefundPermissionAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("refund-api-user")
        self.client = APIClient()

    def test_refund_queue_requires_explicit_permission(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/payments/refunds/")
        self.assertEqual(response.status_code, 403)

    def test_refund_creation_requires_explicit_permission(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/payments/refunds/", {
            "return_request_id": 1,
            "amount": 1000,
            "idempotency_key": str(uuid4()),
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_refund_queue_serializes_jalali_timestamps(self):
        user = User.objects.create_user("refund-queue-customer")
        staff = self.user
        order = Order.objects.create(
            user=user, first_name="Test", last_name="Customer",
            mobile="09123456789", province="tehran", city="Tehran",
            address="Test address", subtotal=Decimal("100000"),
            vat_amount=Decimal("10000"), total_amount=Decimal("110000"),
            status="delivered",
        )
        payment = Payment.objects.create(
            order=order, gateway="mock", amount=Decimal("110000"),
            status="success", ref_id="REFUND-QUEUE-CAPTURE",
        )
        return_request = ReturnRequest.objects.create(
            order=order, user=user, reason="مرجوعی", status="received",
        )
        refund = create_refund(
            return_request_id=return_request.pk, amount=Decimal("10000"),
            actor=staff, idempotency_key=uuid4(),
        )
        permission = Permission.objects.get(
            content_type__app_label="payments", codename="can_manage_refunds",
        )
        staff.user_permissions.add(permission)
        self.client.force_authenticate(user=staff)
        response = self.client.get("/api/payments/refunds/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["id"], refund.pk)
        self.assertIsInstance(response.data[0]["created_at"], str)
        self.assertIsInstance(response.data[0]["history"][0]["created_at"], str)

    def test_refund_permission_grants_access_to_queue(self):
        permission = Permission.objects.get(
            content_type__app_label="payments",
            codename="can_manage_refunds",
        )
        self.user.user_permissions.add(permission)
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/payments/refunds/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])



class RefundConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.user = User.objects.create_user("refund-concurrency-customer")
        self.staff = User.objects.create_user("refund-concurrency-staff")
        self.order = Order.objects.create(
            user=self.user, first_name="Test", last_name="Customer",
            mobile="09123456789", province="tehran", city="Tehran",
            address="Test address", subtotal=Decimal("100000"),
            vat_amount=Decimal("10000"), total_amount=Decimal("110000"),
            status="delivered",
        )
        self.payment = Payment.objects.create(
            order=self.order, gateway="mock", amount=Decimal("110000"),
            status="success", ref_id="CONCURRENT-CAPTURE",
        )
        self.return_request = ReturnRequest.objects.create(
            order=self.order, user=self.user, reason="مرجوعی", status="received",
        )
        self.request_id = self.return_request.pk
        self.staff_id = self.staff.pk

    def test_concurrent_refund_reservations_cannot_exceed_captured_amount(self):
        def reserve(amount):
            close_old_connections()
            try:
                actor = User.objects.get(pk=self.staff_id)
                try:
                    create_refund(
                        return_request_id=self.request_id,
                        amount=Decimal(amount),
                        actor=actor,
                        idempotency_key=uuid4(),
                    )
                    return "created"
                except RefundError:
                    return "rejected"
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(reserve, ["70000", "50000"]))

        self.assertCountEqual(results, ["created", "rejected"])
        reserved_total = sum(
            Refund.objects.exclude(status__in=["failed", "rejected", "succeeded"])
            .values_list("amount", flat=True),
            Decimal("0"),
        )
        self.assertLessEqual(reserved_total, self.payment.amount)
