import random
import string
from django.conf import settings
from django.db import transaction
from django.urls import reverse
from payments.models import MockGatewayTransaction, Payment
from .base import BaseGateway, PaymentResult


class MockGateway(BaseGateway):
    @transaction.atomic
    def request(self, payment, request_key):
        payment = Payment.objects.select_for_update().get(
            pk=payment.pk,
        )
        response = payment.gateway_response or {}

        existing_authority = response.get("authority")
        existing_redirect_url = response.get("redirect_url")
        existing_request_key = response.get("request_key")

        if existing_authority or existing_redirect_url or existing_request_key:
            if (
                existing_request_key == str(request_key)
                and existing_authority
                and existing_redirect_url
            ):
                mock_transaction = MockGatewayTransaction.objects.filter(
                    payment=payment,
                    authority=existing_authority,
                ).first()

                if mock_transaction:
                    return PaymentResult(
                        success=True,
                        redirect_url=existing_redirect_url,
                        authority=existing_authority,
                        message="Existing mock payment session reused",
                        raw_response=response,
                    )

            return PaymentResult(
                success=False,
                outcome_unknown=True,
                message="Existing payment request has an unresolved state",
                raw_response=response,
            )

        mock_transaction = MockGatewayTransaction.objects.filter(
            payment=payment,
        ).first()

        if mock_transaction:
            stored_request_key = (mock_transaction.raw_response or {}).get(
                "request_key"
            )

            if stored_request_key == str(request_key) and mock_transaction.authority:
                redirect_url = settings.MOCK_PAYMENT_BASE_URL + reverse(
                    "mock-payment-page",
                    args=[payment.id],
                )

                return PaymentResult(
                    success=True,
                    redirect_url=redirect_url,
                    authority=mock_transaction.authority,
                    message="Existing mock payment session recovered",
                    raw_response={
                        **(mock_transaction.raw_response or {}),
                        "step": "request",
                        "authority": mock_transaction.authority,
                        "redirect_url": redirect_url,
                        "request_key": str(request_key),
                    },
                )

            return PaymentResult(
                success=False,
                outcome_unknown=True,
                message="Existing mock transaction has an unresolved state",
                raw_response={
                    "step": "request",
                    "authority": mock_transaction.authority,
                },
            )

        authority = "MOCK-" + "".join(
            random.choices(
                string.ascii_uppercase + string.digits,
                k=12,
            )
        )

        redirect_url = settings.MOCK_PAYMENT_BASE_URL + reverse(
            "mock-payment-page", args=[payment.id]
        )

        mock_transaction = MockGatewayTransaction.objects.create(
            payment=payment,
            authority=authority,
            status="pending",
            raw_response={
                "step": "request",
                "authority": authority,
                "request_key": str(request_key),
            },
        )

        return PaymentResult(
            success=True,
            redirect_url=redirect_url,
            authority=authority,
            message="Mock payment initiated",
            raw_response={
                "step": "request",
                "authority": authority,
                "redirect_url": redirect_url,
                "request_key": str(request_key),
            },
        )

    def verify(self, payment, params=None):
        params = params or {}
        authority = params.get("authority", "")

        transaction = MockGatewayTransaction.objects.filter(
            payment=payment,
            authority=authority,
        ).first()

        if not transaction:
            return PaymentResult(
                success=False,
                outcome_unknown=True,
                message="Mock transaction not found",
                raw_response={
                    "step": "verify",
                    "authority": authority,
                },
            )

        if transaction.status == "success":
            return PaymentResult(
                success=True,
                ref_id=transaction.ref_id,
                message="Mock payment verified",
                raw_response=transaction.raw_response,
            )

        if transaction.status == "failed":
            return PaymentResult(
                success=False,
                message="Mock payment failed or cancelled",
                raw_response=transaction.raw_response,
            )

        return PaymentResult(
            success=False,
            outcome_unknown=True,
            message="Mock transaction is still pending",
            raw_response=transaction.raw_response,
        )

    def inquire(self, payment, request_key):
        transaction = MockGatewayTransaction.objects.filter(
            payment=payment,
        ).first()

        if transaction:
            stored_request_key = (transaction.raw_response or {}).get("request_key")
            if stored_request_key == str(request_key) and transaction.authority:
                redirect_url = settings.MOCK_PAYMENT_BASE_URL + reverse(
                    "mock-payment-page",
                    args=[payment.id],
                )

                return PaymentResult(
                    success=True,
                    authority=transaction.authority,
                    redirect_url=redirect_url,
                    message="Mock payment session recovered",
                    raw_response={
                        **transaction.raw_response,
                        "step": "inquire",
                        "redirect_url": redirect_url,
                    },
                )

        return PaymentResult(
            success=False,
            outcome_unknown=True,
            message="Mock payment request could not be identified",
            raw_response={
                "step": "inquire",
                "request_key": str(request_key),
            },
        )

    def inquire_transaction(self, payment):
        transaction = MockGatewayTransaction.objects.filter(
            payment=payment,
        ).first()

        if not transaction:
            return PaymentResult(
                success=False,
                outcome_unknown=True,
                message="Mock transaction not found",
                raw_response={
                    "step": "inquire_transaction",
                    "authority": payment.authority,
                },
            )

        if transaction.status == "success":
            return PaymentResult(
                success=True,
                ref_id=transaction.ref_id,
                message="Mock transaction inquiry successful",
                raw_response=transaction.raw_response,
            )

        if transaction.status == "failed":
            return PaymentResult(
                success=False,
                message="Mock transaction failed",
                raw_response=transaction.raw_response,
            )

        return PaymentResult(
            success=False,
            outcome_unknown=True,
            message="Mock transaction status is pending",
            raw_response=transaction.raw_response,
        )
