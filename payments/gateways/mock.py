import random
import string
from django.conf import settings
from django.urls import reverse
from .base import BaseGateway, PaymentResult


class MockGateway(BaseGateway):
    def request(self, payment):
        authority = 'MOCK-' + ''.join(
            random.choices(string.ascii_uppercase + string.digits, k=12)
        )
        redirect_url = (
            settings.MOCK_PAYMENT_BASE_URL
            + reverse('mock-payment-page', args=[payment.id])
        )
        return PaymentResult(
            success=True,
            redirect_url=redirect_url,
            authority=authority,
            message='Mock payment initiated',
            raw_response={'step': 'request', 'authority': authority},
        )

    def verify(self, payment, params=None):
        params = params or {}
        status = params.get('status', '')
        authority = params.get('authority', '')

        # Real gateways would call the bank API here with authority.
        # Mock just trusts the status from the mock page.
        if status == 'success' and authority == payment.authority:
            ref_id = 'MOCK-REF-' + ''.join(
                random.choices(string.digits, k=10)
            )
            return PaymentResult(
                success=True,
                ref_id=ref_id,
                message='Mock payment verified',
                raw_response={
                    'step': 'verify',
                    'status': 'success',
                    'ref_id': ref_id,
                },
            )

        return PaymentResult(
            success=False,
            message='Mock payment cancelled or failed',
            raw_response={
                'step': 'verify',
                'status': status,
                'authority': authority,
            },
        )