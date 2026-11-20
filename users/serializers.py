from rest_framework import serializers
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from .sms import send_otp_sms, SMSDeliveryError
from django.contrib.auth.hashers import check_password
from django.conf import settings
from .models import Profile, OTPCode, OTPRequestLimit


class RequestOTPSerializer(serializers.Serializer):
    mobile = serializers.RegexField(
        r"^09[0-9]{9}$",
        error_messages={"invalid": "شماره موبایل معتبر نیست. (مثال: 09121234567)"},
    )

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

                if elapsed < 60:
                    wait = max(1, int(60 - elapsed))
                    raise serializers.ValidationError(
                        {"detail": f"لطفاً {wait} ثانیه دیگر تلاش کنید."}
                    )

            otp, raw_code = OTPCode.create_for_mobile(mobile)

            limit.last_requested_at = now
            limit.save(update_fields=["last_requested_at"])

        try:
            send_otp_sms(mobile, raw_code)
        except SMSDeliveryError:
            otp.is_used = True
            otp.save(update_fields=["is_used"])

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

    def create(self, validated_data):
        mobile = validated_data["mobile"]
        code = validated_data["code"]
        error = None
        user = None

        with transaction.atomic():
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
