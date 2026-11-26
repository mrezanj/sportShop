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
from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone
from django.core.cache import cache
from django.core.management import call_command
from django.core.exceptions import ImproperlyConfigured
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from rest_framework.exceptions import ValidationError
from .sms import SMSDeliveryError
from .models import OTPCode, Profile, OTPRequestLimit, OTPFailedAttempt
from .serializers import RequestOTPSerializer, VerifyOTPSerializer
from .throttles import OTPRequestThrottle, ThrottleBackendUnavailable
from redis.exceptions import ConnectionError


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

    @override_settings(DEBUG=False)
    def test_improperly_configured_sms_backend_invalidates_otp(self):
        with patch(
            "users.serializers.send_otp_sms",
            side_effect=ImproperlyConfigured("Invalid SMS backend"),
        ):
            serializer = RequestOTPSerializer(data={"mobile": self.mobile})
            serializer.is_valid(raise_exception=True)

            with self.assertRaises(ImproperlyConfigured):
                serializer.save()

        otp = OTPCode.objects.get(mobile=self.mobile)

        self.assertTrue(otp.is_used)

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
        self.assertIn("is_staff", response.data["user"])
        self.assertIn("is_employee", response.data["user"])
        self.assertFalse(response.data["user"]["is_staff"])
        self.assertFalse(response.data["user"]["is_employee"])
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)
        user = User.objects.get(username=self.mobile)
        self.assertTrue(Profile.objects.filter(user=user, mobile=self.mobile).exists())
        customer_group = Group.objects.get(name="مشتری")
        self.assertTrue(user.groups.filter(pk=customer_group.pk).exists())
        self.assertFalse(customer_group.permissions.exists())

    def test_existing_user_otp_login_preserves_existing_roles(self):
        user = User.objects.create_user(
            username=self.mobile,
            password="test-password",
        )
        Profile.objects.create(user=user, mobile=self.mobile)
        legacy_group = Group.objects.create(name="آزمایش انبار - مدیر")
        accountant_group = Group.objects.create(name="حسابدار")
        user.groups.add(legacy_group, accountant_group)
        otp = self.create_otp()

        response = self.client.post(
            "/api/auth/verify-otp/",
            {"mobile": self.mobile, "code": self.raw_code},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertQuerySetEqual(
            user.groups.order_by("name").values_list("name", flat=True),
            sorted(["آزمایش انبار - مدیر", "حسابدار"]),
            transform=lambda value: value,
        )
        self.assertFalse(user.groups.filter(name="مشتری").exists())
        otp.refresh_from_db()
        self.assertTrue(otp.is_used)

    def test_existing_username_without_profile_is_not_reclassified_as_customer(self):
        user = User.objects.create_user(
            username=self.mobile,
            password="test-password",
        )
        legacy_group = Group.objects.create(name="آزمایش انبار - ثبت کننده")
        user.groups.add(legacy_group)
        self.create_otp()

        response = self.client.post(
            "/api/auth/verify-otp/",
            {"mobile": self.mobile, "code": self.raw_code},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.groups.filter(pk=legacy_group.pk).exists())
        self.assertFalse(user.groups.filter(name="مشتری").exists())
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

    def test_aggregate_failed_attempt_limit_blocks_correct_otp(self):
        for _ in range(10):
            OTPFailedAttempt.objects.create(mobile=self.mobile)

        otp = self.create_otp()

        response = self.client.post(
            "/api/auth/verify-otp/",
            {"mobile": self.mobile, "code": self.raw_code},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            OTPFailedAttempt.objects.filter(mobile=self.mobile).count(),
            10,
        )

        otp.refresh_from_db()
        self.assertEqual(otp.attempt_count, 0)
        self.assertFalse(otp.is_used)

    def test_aggregate_failed_attempt_limit_ignores_attempts_older_than_one_hour(self):
        old_attempt_time = timezone.now() - timedelta(hours=1, seconds=1)

        OTPFailedAttempt.objects.bulk_create(
            [
                OTPFailedAttempt(
                    mobile=self.mobile,
                    created_at=old_attempt_time,
                )
                for _ in range(10)
            ]
        )

        otp = self.create_otp()

        response = self.client.post(
            "/api/auth/verify-otp/",
            {"mobile": self.mobile, "code": self.raw_code},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])

        otp.refresh_from_db()
        self.assertTrue(otp.is_used)

    def test_cleanup_otp_failed_attempts_deletes_only_old_records(self):
        old_attempt = OTPFailedAttempt.objects.create(
            mobile=self.mobile,
            created_at=timezone.now() - timedelta(hours=1, seconds=1),
        )
        recent_attempt = OTPFailedAttempt.objects.create(
            mobile=self.mobile,
            created_at=timezone.now(),
        )

        call_command("cleanup_otp_failed_attempts")

        self.assertFalse(OTPFailedAttempt.objects.filter(pk=old_attempt.pk).exists())
        self.assertTrue(OTPFailedAttempt.objects.filter(pk=recent_attempt.pk).exists())

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

    def test_me_marks_business_role_as_employee_without_django_staff_access(self):
        user = User.objects.create_user(
            username="business-role-user",
            password="test-password",
            is_staff=False,
        )
        group = Group.objects.create(name="حسابدار")
        user.groups.add(group)
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_staff"])
        self.assertTrue(response.data["is_employee"])

    def test_me_does_not_mark_customer_group_as_employee(self):
        user = User.objects.create_user(
            username="customer-role-user",
            password="test-password",
            is_staff=False,
        )
        group = Group.objects.create(name="مشتری")
        user.groups.add(group)
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        response = self.client.get("/api/auth/me/")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["is_staff"])
        self.assertFalse(response.data["is_employee"])

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
        self.assertIn("Retry-After", response)
        self.assertGreater(int(response["Retry-After"]), 0)

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

    def test_hourly_otp_limit(self):
        now = timezone.now()

        OTPRequestLimit.objects.create(
            mobile=self.mobile,
            purpose="login",
            last_requested_at=now - timedelta(seconds=61),
        )

        for minutes in range(5):
            otp = self.create_otp()
            OTPCode.objects.filter(pk=otp.pk).update(
                created_at=now - timedelta(minutes=minutes + 2)
            )

        serializer = RequestOTPSerializer(data={"mobile": self.mobile})
        serializer.is_valid(raise_exception=True)

        with patch("users.serializers.send_otp_sms") as mock_sms:
            with self.assertRaises(ValidationError) as context:
                serializer.save()

        self.assertIn("سقف درخواست", str(context.exception))
        mock_sms.assert_not_called()

        self.assertEqual(
            OTPCode.objects.filter(
                mobile=self.mobile,
                purpose="login",
            ).count(),
            5,
        )

    def test_daily_otp_limit(self):
        now = timezone.now()

        OTPRequestLimit.objects.create(
            mobile=self.mobile,
            purpose="login",
            last_requested_at=now - timedelta(seconds=61),
        )

        for hours in range(2, 12):
            otp = self.create_otp()
            OTPCode.objects.filter(pk=otp.pk).update(
                created_at=now - timedelta(hours=hours)
            )

        serializer = RequestOTPSerializer(data={"mobile": self.mobile})
        serializer.is_valid(raise_exception=True)

        with patch("users.serializers.send_otp_sms") as mock_sms:
            with self.assertRaises(ValidationError) as context:
                serializer.save()

        self.assertIn("سقف درخواست", str(context.exception))
        mock_sms.assert_not_called()

        self.assertEqual(
            OTPCode.objects.filter(
                mobile=self.mobile,
                purpose="login",
            ).count(),
            10,
        )

    def test_hourly_limit_resets_after_one_hour(self):
        now = timezone.now()

        OTPRequestLimit.objects.create(
            mobile=self.mobile,
            purpose="login",
            last_requested_at=now - timedelta(seconds=61),
        )

        for hours in range(2, 7):
            otp = self.create_otp()
            OTPCode.objects.filter(pk=otp.pk).update(
                created_at=now - timedelta(hours=hours)
            )

        serializer = RequestOTPSerializer(data={"mobile": self.mobile})
        serializer.is_valid(raise_exception=True)

        with patch("users.serializers.send_otp_sms"):
            result = serializer.save()

        self.assertEqual(result["mobile"], self.mobile)

        self.assertEqual(
            OTPCode.objects.filter(
                mobile=self.mobile,
                purpose="login",
            ).count(),
            6,
        )

    def test_profile_rejects_future_birth_date(self):
        user = User.objects.create_user(
            username="profile-test-user",
            password="test-password",
        )
        Profile.objects.create(
            user=user,
            mobile="09129999999",
        )
        self.client.force_authenticate(user=user)

        future_date = timezone.localdate() + timedelta(days=1)

        response = self.client.patch(
            "/api/auth/profile/",
            {"birth_date": future_date.isoformat()},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("birth_date", response.data)

        profile = Profile.objects.get(user=user)
        self.assertIsNone(profile.birth_date)

    def test_profile_updates_and_returns_birth_date(self):
        user = User.objects.create_user(
            username="profile-update-user",
            password="test-password",
        )
        profile = Profile.objects.create(
            user=user,
            mobile="09128888888",
        )
        self.client.force_authenticate(user=user)

        birth_date = timezone.localdate().replace(year=timezone.localdate().year - 25)

        response = self.client.patch(
            "/api/auth/profile/",
            {
                "birth_date": birth_date.isoformat(),
                "mobile": "09127777777",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["birth_date"], birth_date.isoformat())
        self.assertEqual(response.data["mobile"], "09128888888")

        profile.refresh_from_db()
        self.assertEqual(profile.birth_date, birth_date)
        self.assertEqual(profile.mobile, "09128888888")

        response = self.client.get("/api/auth/profile/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["birth_date"], birth_date.isoformat())

    def test_profile_updates_and_returns_customer_name(self):
        user = User.objects.create_user(
            username="profile-name-user",
            password="test-password",
        )
        profile = Profile.objects.create(
            user=user,
            mobile="09123334444",
        )
        self.client.force_authenticate(user=user)

        response = self.client.patch(
            "/api/auth/profile/",
            {"first_name": " رضا ", "last_name": " محمدی "},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["first_name"], "رضا")
        self.assertEqual(response.data["last_name"], "محمدی")
        self.assertEqual(response.data["mobile"], "09123334444")

        user.refresh_from_db()
        self.assertEqual(user.first_name, "رضا")
        self.assertEqual(user.last_name, "محمدی")

        response = self.client.get("/api/auth/profile/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["first_name"], "رضا")
        self.assertEqual(response.data["last_name"], "محمدی")

    def test_profile_requires_authentication(self):
        response = self.client.get("/api/auth/profile/")
        self.assertEqual(response.status_code, 401)

        response = self.client.patch(
            "/api/auth/profile/",
            {"birth_date": "2000-01-01"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_profile_returns_404_when_profile_does_not_exist(self):
        user = User.objects.create_user(
            username="user-without-profile",
            password="test-password",
        )
        self.client.force_authenticate(user=user)

        response = self.client.get("/api/auth/profile/")

        self.assertEqual(response.status_code, 404)

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

    def test_concurrent_otp_requests_respect_hourly_limit(self):
        now = timezone.now()

        OTPRequestLimit.objects.create(
            mobile=self.mobile,
            purpose="login",
            last_requested_at=now - timedelta(seconds=61),
        )

        for _ in range(4):
            OTPCode.objects.create(
                mobile=self.mobile,
                code=make_password(self.raw_code),
                purpose="login",
                expires_at=now + timedelta(minutes=2),
            )

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
                created_at__gte=now - timedelta(hours=1),
            ).count(),
            5,
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

    def test_concurrent_failed_verifications_respect_aggregate_limit(self):
        OTPFailedAttempt.objects.bulk_create(
            [OTPFailedAttempt(mobile=self.mobile) for _ in range(9)]
        )

        otp = OTPCode.objects.create(
            mobile=self.mobile,
            code=make_password(self.raw_code),
            purpose="login",
            expires_at=timezone.now() + timedelta(minutes=2),
        )

        def verify_wrong_code():
            try:
                serializer = VerifyOTPSerializer(
                    data={
                        "mobile": self.mobile,
                        "code": "654321",
                    }
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()
                return "success"
            except ValidationError:
                return "rejected"

        results = self.run_concurrently(verify_wrong_code)

        self.assertCountEqual(results, ["rejected", "rejected"])

        self.assertEqual(
            OTPFailedAttempt.objects.filter(mobile=self.mobile).count(),
            10,
        )

        otp.refresh_from_db()
        self.assertEqual(otp.attempt_count, 1)
        self.assertFalse(otp.is_used)


class OTPThrottleConcurrencyTests(TransactionTestCase):
    ip = "198.51.100.77"
    request_count = 40
    expected_allowed = 10

    def test_wait_returns_none_when_redis_key_does_not_exist(self):
        throttle = OTPRequestThrottle()
        throttle.key = "throttle_test_key"

        with patch.object(
            throttle.cache._cache,
            "get_client",
        ) as mock_get_client:
            mock_get_client.return_value.ttl.return_value = -2

            self.assertIsNone(throttle.wait())

    def test_wait_rejects_redis_key_without_expiration(self):
        throttle = OTPRequestThrottle()
        throttle.key = "throttle_test_key"

        with patch.object(
            throttle.cache._cache,
            "get_client",
        ) as mock_get_client:
            mock_get_client.return_value.ttl.return_value = -1

            with self.assertRaises(ThrottleBackendUnavailable):
                throttle.wait()

    def test_redis_failure_in_wait_raises_service_unavailable(self):
        throttle = OTPRequestThrottle()
        throttle.key = "throttle_test_key"

        with patch.object(
            throttle.cache._cache,
            "get_client",
            side_effect=ConnectionError("Redis unavailable"),
        ):
            with self.assertRaises(ThrottleBackendUnavailable) as context:
                throttle.wait()

        self.assertEqual(context.exception.status_code, 503)

    def test_redis_failure_raises_service_unavailable(self):
        throttle = OTPRequestThrottle()
        request = type(
            "Request",
            (),
            {
                "META": {"REMOTE_ADDR": self.ip},
                "headers": {},
            },
        )()

        with patch.object(
            throttle.cache._cache,
            "get_client",
            side_effect=ConnectionError("Redis unavailable"),
        ):
            with self.assertRaises(ThrottleBackendUnavailable) as context:
                throttle.allow_request(request, view=None)

        self.assertEqual(context.exception.status_code, 503)

    def test_concurrent_requests_respect_atomic_ip_limit(self):
        throttle = OTPRequestThrottle()
        cache_key = throttle.cache_format % {
            "scope": throttle.scope,
            "ident": self.ip,
        }

        cache.delete(cache_key)
        self.addCleanup(cache.delete, cache_key)

        barrier = Barrier(self.request_count)

        def attempt():
            close_old_connections()
            try:
                request = type(
                    "Request",
                    (),
                    {
                        "META": {"REMOTE_ADDR": self.ip},
                        "headers": {},
                    },
                )()

                local_throttle = OTPRequestThrottle()
                barrier.wait(timeout=30)

                return local_throttle.allow_request(request, view=None)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=self.request_count) as executor:
            results = list(
                executor.map(
                    lambda _: attempt(),
                    range(self.request_count),
                )
            )

        self.assertEqual(
            sum(results),
            self.expected_allowed,
        )

from django.contrib.auth.models import Group, Permission
from django.test import TestCase


class StaffRoleSetupCommandTests(TestCase):
    def test_command_is_idempotent_and_creates_roles(self):
        call_command("setup_staff_roles")
        call_command("setup_staff_roles")
        expected = {"مدیرعامل", "رئیس هیئت‌مدیره", "مدیر داخلی", "حسابدار", "مشاور", "مشتری"}
        self.assertTrue(expected.issubset(set(Group.objects.values_list("name", flat=True))))
        self.assertEqual(Group.objects.filter(name__in=expected).count(), len(expected))
        customer = Group.objects.get(name="مشتری")
        self.assertFalse(customer.permissions.exists())

    def test_executives_have_equal_business_permissions_without_auth_admin(self):
        call_command("setup_staff_roles")
        ceo = Group.objects.get(name="مدیرعامل")
        chair = Group.objects.get(name="رئیس هیئت‌مدیره")
        self.assertEqual(set(ceo.permissions.values_list("id", flat=True)), set(chair.permissions.values_list("id", flat=True)))
        self.assertTrue(ceo.permissions.filter(content_type__app_label="catalog").exists())
        self.assertFalse(ceo.permissions.filter(content_type__app_label="auth").exists())
        self.assertFalse(
            ceo.permissions.filter(
                content_type__model__in=("otpcode", "otpfailedattempt", "otprequestlimit", "profile")
            ).exists()
        )
        self.assertFalse(ceo.permissions.filter(codename__startswith="delete_").exists())

    def test_accountant_and_internal_manager_permissions_are_separated(self):
        call_command("setup_staff_roles")
        accountant = Group.objects.get(name="حسابدار")
        internal = Group.objects.get(name="مدیر داخلی")
        self.assertTrue(accountant.permissions.filter(codename="can_review_inventory_document").exists())
        self.assertFalse(accountant.permissions.filter(codename="can_approve_inventory_document").exists())
        self.assertTrue(internal.permissions.filter(codename="can_approve_inventory_document").exists())
        self.assertFalse(internal.permissions.filter(codename="can_review_inventory_document").exists())


class StaffRoleManagementAPITests(APITestCase):
    def setUp(self):
        call_command("setup_staff_roles")
        self.executive = User.objects.create_user(
            username="staff-executive",
            password="test-password",
        )
        self.executive.groups.add(Group.objects.get(name="مدیرعامل"))
        self.token = Token.objects.create(user=self.executive)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")

        self.target = User.objects.create_user(
            username="09120000001",
            password="test-password",
        )
        Profile.objects.create(user=self.target, mobile="09120000001")

    def test_executive_can_list_users_and_assign_business_role(self):
        response = self.client.get("/api/auth/staff/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any(row["id"] == self.target.pk for row in response.data["results"]))

        response = self.client.patch(
            f"/api/auth/staff/{self.target.pk}/role/",
            {"role": "حسابدار"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["changed"])
        self.assertEqual(response.data["user"]["roles"], ["حسابدار"])
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_staff)
        self.assertFalse(self.target.is_superuser)

    def test_assigning_customer_removes_legacy_groups_and_direct_permissions(self):
        legacy_group = Group.objects.create(name="آزمایش انبار - مدیر")
        permission = Permission.objects.filter(codename="add_user").first()
        if permission is None:
            permission = Permission.objects.create(
                name="Test direct permission",
                codename="test_direct_permission",
                content_type=ContentType.objects.get_for_model(User),
            )
        legacy_group.permissions.add(permission)
        self.target.groups.add(legacy_group)
        self.target.user_permissions.add(permission)

        response = self.client.patch(
            f"/api/auth/staff/{self.target.pk}/role/",
            {"role": "مشتری"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(
            list(self.target.groups.values_list("name", flat=True)),
            ["مشتری"],
        )
        self.assertFalse(self.target.user_permissions.exists())
        self.assertFalse(self.target.has_perm(f"{permission.content_type.app_label}.{permission.codename}"))

    def test_reassigning_same_role_still_clears_direct_permissions(self):
        customer = Group.objects.get(name="مشتری")
        permission = Permission.objects.filter(codename="add_user").first()
        self.target.groups.add(customer)
        self.target.user_permissions.add(permission)

        response = self.client.patch(
            f"/api/auth/staff/{self.target.pk}/role/",
            {"role": "مشتری"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["changed"])
        self.target.refresh_from_db()
        self.assertFalse(self.target.user_permissions.exists())

    def test_assigning_staff_role_replaces_customer_and_legacy_groups(self):
        customer = Group.objects.get(name="مشتری")
        legacy = Group.objects.create(name="Inventory Creators")
        self.target.groups.add(customer, legacy)

        response = self.client.patch(
            f"/api/auth/staff/{self.target.pk}/role/",
            {"role": "حسابدار"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.target.refresh_from_db()
        self.assertEqual(
            list(self.target.groups.values_list("name", flat=True)),
            ["حسابدار"],
        )

    def test_role_assignment_is_idempotent_and_does_not_duplicate_audit(self):
        url = f"/api/auth/staff/{self.target.pk}/role/"
        first = self.client.patch(url, {"role": "مشاور"}, format="json")
        self.assertEqual(first.status_code, 200)
        second = self.client.patch(url, {"role": "مشاور"}, format="json")
        self.assertEqual(second.status_code, 200)
        self.assertFalse(second.data["changed"])
        self.assertEqual(
            self.client.get("/api/auth/staff/history/").data.__len__(),
            1,
        )

    def test_executive_cannot_change_own_role(self):
        response = self.client.patch(
            f"/api/auth/staff/{self.executive.pk}/role/",
            {"role": "مشتری"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self.executive.groups.filter(name="مدیرعامل").exists())

    def test_superuser_role_cannot_be_changed(self):
        target = User.objects.create_superuser(
            username="protected-superuser",
            email="root@example.com",
            password="test-password",
        )
        response = self.client.patch(
            f"/api/auth/staff/{target.pk}/role/",
            {"role": "مشتری"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_non_executive_cannot_list_or_assign_staff_roles(self):
        accountant = User.objects.create_user(
            username="staff-accountant",
            password="test-password",
        )
        accountant.groups.add(Group.objects.get(name="حسابدار"))
        token = Token.objects.create(user=accountant)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        self.assertEqual(self.client.get("/api/auth/staff/").status_code, 403)
        self.assertEqual(
            self.client.patch(
                f"/api/auth/staff/{self.target.pk}/role/",
                {"role": "مشتری"},
                format="json",
            ).status_code,
            403,
        )

    def test_customer_cannot_access_staff_management_apis(self):
        customer = User.objects.create_user(
            username="staff-customer",
            password="test-password",
        )
        customer.groups.add(Group.objects.get(name="مشتری"))
        token = Token.objects.create(user=customer)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        self.assertEqual(self.client.get("/api/auth/staff/").status_code, 403)
        self.assertEqual(self.client.get("/api/auth/staff/history/").status_code, 403)
        self.assertEqual(
            self.client.patch(
                f"/api/auth/staff/{self.target.pk}/role/",
                {"role": "حسابدار"},
                format="json",
            ).status_code,
            403,
        )

    def test_role_history_records_actor_and_previous_role(self):
        self.target.groups.add(Group.objects.get(name="مشتری"))
        response = self.client.patch(
            f"/api/auth/staff/{self.target.pk}/role/",
            {"role": "مدیر داخلی"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        history = self.client.get("/api/auth/staff/history/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.data), 1)
        self.assertEqual(history.data[0]["previous_roles"], ["مشتری"])
        self.assertEqual(history.data[0]["new_role"], "مدیر داخلی")


    def test_me_exposes_staff_management_capability_only_to_executives(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["can_manage_staff"])

        accountant = User.objects.create_user(
            username="staff-accountant-me",
            password="test-password",
        )
        accountant.groups.add(Group.objects.get(name="حسابدار"))
        token = Token.objects.create(user=accountant)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["can_manage_staff"])


class NormalizeStaffRolesCommandTests(TestCase):
    def setUp(self):
        call_command("setup_staff_roles")

    def test_legacy_only_accounts_become_customers_and_direct_grants_are_cleared(self):
        user = User.objects.create_user(
            username="legacy-only-user",
            password="test-password",
        )
        legacy = Group.objects.create(name="Inventory Creators")
        permission = Permission.objects.filter(codename="add_user").first()
        if permission is None:
            permission = Permission.objects.create(
                name="Test direct permission",
                codename="normalize_test_permission",
                content_type=ContentType.objects.get_for_model(User),
            )
        legacy.permissions.add(permission)
        user.groups.add(legacy)
        user.user_permissions.add(permission)

        call_command("normalize_staff_roles")

        user.refresh_from_db()
        self.assertEqual(
            list(user.groups.values_list("name", flat=True)),
            ["مشتری"],
        )
        self.assertFalse(user.user_permissions.exists())
        self.assertFalse(Group.objects.get(name="مشتری").permissions.exists())

    def test_single_official_role_is_preserved_and_legacy_groups_are_removed(self):
        user = User.objects.create_user(
            username="legacy-accountant",
            password="test-password",
        )
        accountant = Group.objects.get(name="حسابدار")
        legacy = Group.objects.create(name="آزمایش انبار - حسابدار")
        user.groups.add(accountant, legacy)

        call_command("normalize_staff_roles")

        user.refresh_from_db()
        self.assertEqual(
            list(user.groups.values_list("name", flat=True)),
            ["حسابدار"],
        )

    def test_conflicting_official_roles_fall_back_to_customer(self):
        user = User.objects.create_user(
            username="conflicting-roles",
            password="test-password",
        )
        user.groups.add(
            Group.objects.get(name="حسابدار"),
            Group.objects.get(name="مدیر داخلی"),
        )

        call_command("normalize_staff_roles")

        user.refresh_from_db()
        self.assertEqual(
            list(user.groups.values_list("name", flat=True)),
            ["مشتری"],
        )

    def test_superuser_groups_and_direct_permissions_are_untouched(self):
        superuser = User.objects.create_superuser(
            username="protected-admin",
            email="admin@example.com",
            password="test-password",
        )
        legacy = Group.objects.create(name="Legacy Admin Group")
        permission = Permission.objects.filter(codename="add_user").first()
        superuser.groups.add(legacy)
        if permission is not None:
            superuser.user_permissions.add(permission)
        before_groups = set(superuser.groups.values_list("pk", flat=True))
        before_permissions = set(
            superuser.user_permissions.values_list("pk", flat=True)
        )

        call_command("normalize_staff_roles")

        superuser.refresh_from_db()
        self.assertEqual(
            set(superuser.groups.values_list("pk", flat=True)),
            before_groups,
        )
        self.assertEqual(
            set(superuser.user_permissions.values_list("pk", flat=True)),
            before_permissions,
        )
