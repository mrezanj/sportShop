import logging

logger = logging.getLogger(__name__)


def send_otp_sms(mobile, code):
    """
    Mock SMS service.
    In development, prints the code to the terminal.
    In production, replace with Kavenegar / MelliPayamak / etc.
    """
    print("\n" + "=" * 60)
    print(f"  SMS به {mobile}")
    print(f"  کد تایید: {code}")
    print("=" * 60 + "\n")
    logger.info(f"OTP for {mobile}: {code}")