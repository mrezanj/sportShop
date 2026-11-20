from rest_framework import serializers
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from .models import Profile, OTPCode
from .sms import send_otp_sms


class RequestOTPSerializer(serializers.Serializer):
    mobile = serializers.RegexField(
        r'^09\d{9}$',
        error_messages={'invalid': 'شماره موبایل معتبر نیست. (مثال: 09121234567)'},
    )

    def validate_mobile(self, value):
        # Rate limiting: max 1 per 60 seconds
        latest = OTPCode.objects.filter(mobile=value).order_by('-created_at').first()
        if latest:
            elapsed = (timezone.now() - latest.created_at).total_seconds()
            if elapsed < 60:
                wait = int(60 - elapsed)
                raise serializers.ValidationError(
                    f'لطفاً {wait} ثانیه دیگر تلاش کنید.'
                )
        return value

    def create(self, validated_data):
        mobile = validated_data['mobile']
        otp = OTPCode.create_for_mobile(mobile)
        send_otp_sms(mobile, otp.code)
        return {'mobile': mobile, 'expires_in': 120}


class VerifyOTPSerializer(serializers.Serializer):
    mobile = serializers.RegexField(r'^09\d{9}$')
    code = serializers.CharField(max_length=6, min_length=6)

    def validate(self, data):
        mobile = data['mobile']
        code = data['code']

        otp = OTPCode.objects.filter(
            mobile=mobile, code=code, is_used=False
        ).order_by('-created_at').first()

        if not otp:
            raise serializers.ValidationError({'code': 'کد وارد شده صحیح نیست.'})

        if not otp.is_valid():
            raise serializers.ValidationError({'code': 'کد منقضی شده است.'})

        data['otp'] = otp
        return data

    def create(self, validated_data):
        mobile = validated_data['mobile']
        otp = validated_data['otp']

        with transaction.atomic():
            otp.is_used = True
            otp.save()

            profile = Profile.objects.filter(mobile=mobile).first()
            if not profile:
                user, created = User.objects.get_or_create(
                    username=mobile,
                    defaults={'is_active': True},
                )
                if not hasattr(user, 'profile'):
                    profile = Profile.objects.create(user=user, mobile=mobile)
            return profile.user