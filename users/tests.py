from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import timedelta
from unittest.mock import patch

from django.test import (
    override_settings,
    TransactionTestCase,
    skipUnlessDBFeature,
)
from django.db import close_old_connections, connections
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from django.core.cache import cache

from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from rest_framework.exceptions import ValidationError

from .sms import SMSDeliveryError
from .models import OTPCode, Profile, OTPRequestLimit
from .serializers import RequestOTPSerializer, VerifyOTPSerializer


class OTPAPITests(APITestCase):
    mobile = "09121234567"
    raw_code = "123456"

    def setUp(self):
        super().setUp()
        cache.clear()

    def create_otp(
        self,
        mobile=None,
        code=None,
        expires_at=None,
        purpose="login",
    ):
        return OTPCode.objects.create(
            mobile=mobile or self.mobile,
            code=make_password(code or self.raw_code),
            purpose=purpose,
            expires_at=expires_at or timezone.now() + timedelta(minutes=2),
        )

    @override_settings(DEBUG=True, OTP_DEBUG_RETURN_CODE=False)
    def test_request_otp_success(self):
        with patch("users.serializers.send_otp_sms") as mock_sms:
            response = self.client.post(
                "/api/auth/request-otp/",
                {"mobile": self.mobile},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["expires_in"], 120)
        self.assertNotIn("debug_otp", response.data)

        otp = OTPCode.objects.get(mobile=self.mobile)
        mock_sms.assert_called_once()

        sent_code = mock_sms.call_args.args[1]

        self.assertTrue(check_password(sent_code, otp.code))
        self.assertNotEqual(otp.code, sent_code)

    def test_register_otp_does_not_block_login_otp_request(self):
        register_otp = self.create_otp(
            purpose="register",
            code="999999",
        )

        with patch("users.serializers.send_otp_sms"):
            response = self.client.post(
                "/api/auth/request-otp/",
                {"mobile": self.mobile},
                format="json",
            )

        self.assertEqual(response.status_code, 200)

        register_otp.refresh_from_db()
        self.assertFalse(register_otp.is_used)

        login_otp = OTPCode.objects.filter(
            mobile=self.mobile,
            purpose="login",
            is_used=False,
        ).first()

        self.assertIsNotNone(login_otp)

    def test_login_verification_ignores_newer_register_otp(self):
        login_otp = self.create_otp(
            purpose="login",
            code=self.raw_code,
        )

        register_otp = self.create_otp(
            purpose="register",
            code="999999",
        )

        response = self.client.post(
            "/api/auth/verify-otp/",
            {"mobile": self.mobile, "code": self.raw_code},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        login_otp.refresh_from_db()
        register_otp.refresh_from_db()

        self.assertTrue(login_otp.is_used)
        self.assertFalse(register_otp.is_used)
        self.assertTrue(response.data["token"])

    @override_settings(DEBUG=True, OTP_DEBUG_RETURN_CODE=True)
    def test_debug_otp_is_returned_when_enabled(self):
        with patch("users.serializers.send_otp_sms") as mock_sms:
            response = self.client.post(
                "/api/auth/request-otp/",
                {"mobile": self.mobile},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("debug_otp", response.data)

        sent_code = mock_sms.call_args.args[1]
        self.assertEqual(response.data["debug_otp"], sent_code)

    @override_settings(DEBUG=False, OTP_DEBUG_RETURN_CODE=True)
    def test_debug_otp_is_not_returned_in_production(self):
        with patch("users.serializers.send_otp_sms") as mock_sms:
            response = self.client.post(
                "/api/auth/request-otp/",
                {"mobile": self.mobile},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("debug_otp", response.data)
        mock_sms.assert_called_once()

    def test_request_otp_sms_failure_invalidates_otp(self):
        with patch(
            "users.serializers.send_otp_sms",
            side_effect=SMSDeliveryError("SMS provider unavailable"),
        ):
            response = self.client.post(
                "/api/auth/request-otp/",
                {"mobile": self.mobile},
                format="json",
            )

        self.assertEqual(response.status_code, 400)

        otp = OTPCode.objects.get(mobile=self.mobile)
        self.assertTrue(otp.is_used)

    def test_request_otp_rejects_invalid_mobile(self):
        response = self.client.post(
            "/api/auth/request-otp/",
            {"mobile": "12345"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_verify_otp_success(self):
        otp = self.create_otp()

        response = self.client.post(
            "/api/auth/verify-otp/",
            {"mobile": self.mobile, "code": self.raw_code},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertTrue(response.data["token"])
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)
        user = User.objects.get(username=self.mobile)
        self.assertTrue(Profile.objects.filter(user=user, mobile=self.mobile).exists())

    def test_wrong_otp_increments_attempt_count(self):
        otp = self.create_otp()

        response = self.client.post(
            "/api/auth/verify-otp/",
            {"mobile": self.mobile, "code": "654321"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

        otp.refresh_from_db()
        self.assertEqual(otp.attempt_count, 1)
        self.assertFalse(otp.is_used)

    def test_five_wrong_attempts_disable_otp(self):
        otp = self.create_otp()

        for _ in range(5):
            response = self.client.post(
                "/api/auth/verify-otp/",
                {"mobile": self.mobile, "code": "654321"},
                format="json",
            )
            self.assertEqual(response.status_code, 400)

        otp.refresh_from_db()
        self.assertEqual(otp.attempt_count, 5)
        self.assertTrue(otp.is_used)

    def test_expired_otp_is_rejected(self):
        otp = self.create_otp(expires_at=timezone.now() - timedelta(minutes=1))

        response = self.client.post(
            "/api/auth/verify-otp/",
            {"mobile": self.mobile, "code": self.raw_code},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)

    def test_inactive_user_cannot_login(self):
        user = User.objects.create_user(
            username=self.mobile,
            password="test-password",
            is_active=False,
        )
        Profile.objects.create(user=user, mobile=self.mobile)
        otp = self.create_otp()

        response = self.client.post(
            "/api/auth/verify-otp/",
            {"mobile": self.mobile, "code": self.raw_code},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)
        self.assertFalse(Token.objects.filter(user=user).exists())

    def test_me_requires_authentication(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 401)

    def test_logout_deletes_auth_token(self):
        user = User.objects.create_user(
            username=self.mobile,
            password="test-password",
        )
        token = Token.objects.create(user=user)

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.post("/api/auth/logout/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Token.objects.filter(user=user).exists())

    def test_request_otp_ip_throttle(self):
        cache.clear()

        with patch("users.serializers.send_otp_sms"):
            for i in range(10):
                mobile = f"09121234{i:03d}"

                response = self.client.post(
                    "/api/auth/request-otp/",
                    {"mobile": mobile},
                    format="json",
                )

                self.assertEqual(response.status_code, 200)

            response = self.client.post(
                "/api/auth/request-otp/",
                {"mobile": "09121234999"},
                format="json",
            )

        self.assertEqual(response.status_code, 429)

    def test_verify_otp_ip_throttle(self):
        cache.clear()

        for _ in range(30):
            response = self.client.post(
                "/api/auth/verify-otp/",
                {
                    "mobile": self.mobile,
                    "code": self.raw_code,
                },
                format="json",
            )

            self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/auth/verify-otp/",
            {
                "mobile": self.mobile,
                "code": self.raw_code,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 429)

    def test_request_otp_cooldown(self):
        with patch("users.serializers.send_otp_sms"):
            first = self.client.post(
                "/api/auth/request-otp/",
                {"mobile": self.mobile},
                format="json",
            )

            second = self.client.post(
                "/api/auth/request-otp/",
                {"mobile": self.mobile},
                format="json",
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)

    def test_request_otp_allowed_after_cooldown(self):
        OTPRequestLimit.objects.create(
            mobile=self.mobile,
            purpose="login",
            last_requested_at=timezone.now() - timedelta(seconds=61),
        )

        with patch("users.serializers.send_otp_sms"):
            response = self.client.post(
                "/api/auth/request-otp/",
                {"mobile": self.mobile},
                format="json",
            )

        self.assertEqual(response.status_code, 200)

    def test_sms_failure_preserves_request_cooldown(self):
        with patch(
            "users.serializers.send_otp_sms",
            side_effect=SMSDeliveryError("SMS provider unavailable"),
        ):
            first = self.client.post(
                "/api/auth/request-otp/",
                {"mobile": self.mobile},
                format="json",
            )

        with patch("users.serializers.send_otp_sms"):
            second = self.client.post(
                "/api/auth/request-otp/",
                {"mobile": self.mobile},
                format="json",
            )

        self.assertEqual(first.status_code, 400)
        self.assertEqual(second.status_code, 400)


@skipUnlessDBFeature("has_select_for_update")
class OTPConcurrencyTests(TransactionTestCase):
    mobile = "09121112233"
    raw_code = "123456"

    def run_concurrently(self, operation):
        barrier = Barrier(2)

        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operation()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(worker),
                executor.submit(worker),
            ]
            return [future.result(timeout=30) for future in futures]

    def test_concurrent_otp_requests_respect_cooldown(self):
        def request_otp():
            try:
                serializer = RequestOTPSerializer(data={"mobile": self.mobile})
                serializer.is_valid(raise_exception=True)
                serializer.save()
                return "success"
            except ValidationError:
                return "rejected"

        with patch("users.serializers.send_otp_sms"):
            results = self.run_concurrently(request_otp)

        self.assertCountEqual(results, ["success", "rejected"])

        self.assertEqual(
            OTPCode.objects.filter(
                mobile=self.mobile,
                purpose="login",
            ).count(),
            1,
        )

        self.assertEqual(
            OTPRequestLimit.objects.filter(
                mobile=self.mobile,
                purpose="login",
            ).count(),
            1,
        )

    def test_concurrent_otp_verification_only_succeeds_once(self):
        otp = OTPCode.objects.create(
            mobile=self.mobile,
            code=make_password(self.raw_code),
            purpose="login",
            expires_at=timezone.now() + timedelta(minutes=2),
        )

        def verify_otp():
            try:
                serializer = VerifyOTPSerializer(
                    data={
                        "mobile": self.mobile,
                        "code": self.raw_code,
                    }
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()
                return "success"
            except ValidationError:
                return "rejected"

        results = self.run_concurrently(verify_otp)

        self.assertCountEqual(results, ["success", "rejected"])

        otp.refresh_from_db()
        self.assertTrue(otp.is_used)
        self.assertEqual(otp.attempt_count, 0)

        self.assertEqual(
            User.objects.filter(username=self.mobile).count(),
            1,
        )

        self.assertEqual(
            Profile.objects.filter(mobile=self.mobile).count(),
            1,
        )
