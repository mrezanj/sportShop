from decimal import Decimal
from uuid import uuid4

from django.contrib.auth.models import User
from django.test import TestCase

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
                amount=Decimal("110001"), actor=self.staff,
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
            amount=Decimal("10000"), actor=self.staff,
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
