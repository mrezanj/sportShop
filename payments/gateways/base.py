from abc import ABC, abstractmethod


class PaymentResult:
    def __init__(
        self,
        success,
        redirect_url=None,
        authority=None,
        ref_id=None,
        message='',
        raw_response=None,
    ):
        self.success = success
        self.redirect_url = redirect_url
        self.authority = authority
        self.ref_id = ref_id
        self.message = message
        self.raw_response = raw_response or {}


class BaseGateway(ABC):
    """Abstract payment gateway interface.

    Any real gateway (Zarinpal, DigiPay, etc.) must implement these methods.
    Switching gateways means only writing a new class in this folder
    and updating ACTIVE_PAYMENT_GATEWAY in settings.
    """

    @abstractmethod
    def request(self, payment):
        """Initiate payment. Return PaymentResult with redirect_url."""
        raise NotImplementedError

    @abstractmethod
    def verify(self, payment, params=None):
        """Verify payment after callback. Return PaymentResult."""
        raise NotImplementedError