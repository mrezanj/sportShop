from abc import ABC, abstractmethod


class PaymentResult:
    def __init__(
        self,
        success,
        redirect_url=None,
        authority=None,
        ref_id=None,
        message="",
        raw_response=None,
        outcome_unknown=False,
    ):
        self.success = success
        self.redirect_url = redirect_url
        self.authority = authority
        self.ref_id = ref_id
        self.message = message
        self.raw_response = {} if raw_response is None else raw_response
        self.outcome_unknown = outcome_unknown


class BaseGateway(ABC):
    """Abstract interface for payment gateways."""

    @abstractmethod
    def request(self, payment, request_key):
        """
        Initiate payment using a stable idempotency key.

        Repeating the same request_key must not create another
        payment session when the provider supports idempotency.
        """
        raise NotImplementedError

    @abstractmethod
    def verify(self, payment, params=None):
        """Verify payment independently with the payment provider."""
        raise NotImplementedError

    @abstractmethod
    def inquire(self, payment, request_key):
        """
        Inquire about a previously submitted payment request.

        Return PaymentResult with:
        - success=True if the payment session is confirmed.
        - outcome_unknown=True if its state cannot be determined.
        - success=False only when failure is definitive.
        """
        raise NotImplementedError

    @abstractmethod
    def inquire_transaction(self, payment):
        """
        Inquire about the final transaction status directly
        from the payment provider.

        Return PaymentResult with:
        - success=True if payment is definitively successful.
        - success=False and outcome_unknown=False if payment
          is definitively unsuccessful.
        - outcome_unknown=True if the transaction state is unknown.
        """
        raise NotImplementedError
