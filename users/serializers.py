from rest_framework import serializers
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from .sms import send_otp_sms, SMSDeliveryError
from django.core.exceptions import ImproperlyConfigured
from django.contrib.auth.hashers import check_password
from django.conf import settings
from .models import Profile, OTPCode, OTPRequestLimit, OTPFailedAttempt
from datetime import timedelta


class RequestOTPSerializer(serializers.Serializer):
    mobile = serializers.RegexField(
        r"^09[0-9]{9}$",
        error_messages={"invalid": "شماره موبایل معتبر نیست. (مثال: 09121234567)"},
    )

    HOURLY_LIMIT = 5
    DAILY_LIMIT = 10
    COOLDOWN_SECONDS = 60

    def create(self, validated_data):
        mobile = validated_data["mobile"]
        purpose = "login"

        with transaction.atomic():
            limit, _ = OTPRequestLimit.objects.get_or_create(
                mobile=mobile,
                purpose=purpose,
            )

            limit = OTPRequestLimit.objects.select_for_update().get(pk=limit.pk)

            now = timezone.now()

            if limit.last_requested_at:
                elapsed = (now - limit.last_requested_at).total_seconds()

                if elapsed < self.COOLDOWN_SECONDS:
                    wait = max(1, int(self.COOLDOWN_SECONDS - elapsed))
                    raise serializers.ValidationError(
                        {"detail": f"لطفاً {wait} ثانیه دیگر تلاش کنید."}
                    )

            recent_requests = OTPCode.objects.filter(
                mobile=mobile,
                purpose=purpose,
            )

            hourly_count = recent_requests.filter(
                created_at__gte=now - timedelta(hours=1),
            ).count()

            if hourly_count >= self.HOURLY_LIMIT:
                raise serializers.ValidationError(
                    {"detail": "سقف درخواست کد تأیید در یک ساعت به پایان رسیده است."}
                )

            daily_count = recent_requests.filter(
                created_at__gte=now - timedelta(hours=24),
            ).count()

            if daily_count >= self.DAILY_LIMIT:
                raise serializers.ValidationError(
                    {"detail": "سقف درخواست کد تأیید در ۲۴ ساعت به پایان رسیده است."}
                )

            otp, raw_code = OTPCode.create_for_mobile(mobile, purpose=purpose)

            limit.last_requested_at = now
            limit.save(update_fields=["last_requested_at"])

        try:
            send_otp_sms(mobile, raw_code)
        except (SMSDeliveryError, ImproperlyConfigured) as exc:
            otp.is_used = True
            otp.save(update_fields=["is_used"])

            if isinstance(exc, ImproperlyConfigured):
                raise

            raise serializers.ValidationError(
                {"detail": "ارسال کد تأیید با مشکل مواجه شد. لطفاً دوباره تلاش کنید."}
            )

        result = {
            "mobile": mobile,
            "expires_in": 120,
        }

        if settings.DEBUG and settings.OTP_DEBUG_RETURN_CODE:
            result["debug_otp"] = raw_code

        return result


class VerifyOTPSerializer(serializers.Serializer):
    mobile = serializers.RegexField(r"^09[0-9]{9}$")
    code = serializers.RegexField(r"^[0-9]{6}$")

    MAX_ATTEMPTS = 5
    MAX_FAILED_ATTEMPTS_PER_HOUR = 10
    FAILED_ATTEMPT_WINDOW = timedelta(hours=1)

    def create(self, validated_data):
        mobile = validated_data["mobile"]
        code = validated_data["code"]
        error = None
        user = None

        with transaction.atomic():
            limit, _ = OTPRequestLimit.objects.get_or_create(
                mobile=mobile,
                purpose="login",
            )

            OTPRequestLimit.objects.select_for_update().get(pk=limit.pk)

            cutoff = timezone.now() - self.FAILED_ATTEMPT_WINDOW

            failed_attempts = OTPFailedAttempt.objects.filter(
                mobile=mobile,
                created_at__gte=cutoff,
            ).count()

            if failed_attempts >= self.MAX_FAILED_ATTEMPTS_PER_HOUR:
                raise serializers.ValidationError(
                    {
                        "code": (
                            "تعداد تلاش‌های ناموفق بیش از حد مجاز است. "
                            "لطفاً بعداً دوباره تلاش کنید."
                        )
                    }
                )
            otp = (
                OTPCode.objects.select_for_update()
                .filter(
                    mobile=mobile,
                    purpose="login",
                    is_used=False,
                )
                .order_by("-created_at")
                .first()
            )

            if not otp:
                error = "کد معتبر نیست یا منقضی شده است."

            elif otp.attempt_count >= self.MAX_ATTEMPTS:
                otp.is_used = True
                otp.save(update_fields=["is_used"])
                error = "تعداد تلاش‌های مجاز به پایان رسیده است."

            elif not otp.is_valid():
                otp.is_used = True
                otp.save(update_fields=["is_used"])
                error = "کد منقضی شده است."

            elif not check_password(code, otp.code):
                otp.attempt_count += 1

                if otp.attempt_count >= self.MAX_ATTEMPTS:
                    otp.is_used = True

                otp.save(update_fields=["attempt_count", "is_used"])
                OTPFailedAttempt.objects.create(mobile=mobile)
                error = "کد وارد شده صحیح نیست."

            else:
                # کد صحیح است؛ در هر شرایطی آن را مصرف می‌کنیم.
                otp.is_used = True
                otp.save(update_fields=["is_used"])

                profile = (
                    Profile.objects.select_related("user").filter(mobile=mobile).first()
                )
                if profile:
                    user = profile.user
                else:
                    user, _ = User.objects.get_or_create(
                        username=mobile,
                        defaults={"is_active": True},
                    )

                    try:
                        profile = user.profile
                    except Profile.DoesNotExist:
                        profile = Profile.objects.create(
                            user=user,
                            mobile=mobile,
                        )

                if user and not user.is_active:
                    error = "حساب کاربری غیرفعال است."

        if error:
            raise serializers.ValidationError({"code": error})

        return user
