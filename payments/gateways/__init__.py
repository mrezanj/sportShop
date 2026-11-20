from django.conf import settings
from .mock import MockGateway


def get_gateway():
    """Return the active gateway instance based on settings."""
    name = getattr(settings, 'ACTIVE_PAYMENT_GATEWAY', 'mock')
    if name == 'mock':
        return MockGateway()
    # Future gateways:
    # if name == 'zarinpal':
    #     from .zarinpal import ZarinpalGateway
    #     return ZarinpalGateway()
    raise ValueError(f'Unknown payment gateway: {name}')