from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .mock import MockGateway


def get_gateway():
    """Return the active gateway instance based on settings."""
    name = getattr(settings, "ACTIVE_PAYMENT_GATEWAY", "").strip().lower()

    if name == "mock":
        if not settings.DEBUG:
            raise ImproperlyConfigured(
                "Mock payment gateway is disabled when DEBUG=False."
            )
        return MockGateway()

    if not name:
        raise ImproperlyConfigured(
            "No payment gateway is configured. "
            "Set ACTIVE_PAYMENT_GATEWAY in the environment."
        )

    # Future gateways:
    # if name == "zarinpal":
    #     from .zarinpal import ZarinpalGateway
    #     return ZarinpalGateway()

    raise ImproperlyConfigured(
        f"Unknown payment gateway: {name}"
    )
