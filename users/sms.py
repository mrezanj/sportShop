
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


class SMSDeliveryError(Exception):
    """Raised when an SMS provider fails to deliver a message."""


def send_otp_sms(mobile, code):
    """
    SMS provider entry point.

    Current provider: Mock
    Future provider: Kavenegar

    Never log or expose OTP codes here.
    """
    backend = getattr(settings, "SMS_BACKEND", "mock")

    if backend == "mock":
        if not settings.DEBUG:
            raise ImproperlyConfigured(
                "Mock SMS backend cannot be used in production."
            )

        return True

    raise ImproperlyConfigured(
        f"Unsupported SMS backend: {backend}"
    )
