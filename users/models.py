from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import secrets
from django.contrib.auth.hashers import make_password
from jalali_suite.models import JalaliDateTimeField


def generate_otp():
    return f"{secrets.randbelow(1_000_000):06d}"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    mobile = models.CharField(max_length=11, unique=True)
    birth_date = models.DateField(null=True, blank=True, verbose_name="تاریخ تولد")
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "پروفایل"
        verbose_name_plural = "پروفایل‌ها"

    def __str__(self):
        return self.mobile


class OTPRequestLimit(models.Model):
    mobile = models.CharField(max_length=11)
    purpose = models.CharField(max_length=20)
    last_requested_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["mobile", "purpose"],
                name="unique_otp_request_limit",
            ),
        ]

    def __str__(self):
        return f"{self.mobile} - {self.purpose}"


class OTPFailedAttempt(models.Model):
    mobile = models.CharField(max_length=11)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["mobile", "created_at"],
                name="otp_fail_mobile_time_idx",
            ),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.mobile} - {self.created_at}"


class OTPCode(models.Model):
    PURPOSE_CHOICES = [
        ("login", "ورود"),
        ("register", "ثبت‌نام"),
    ]
    mobile = models.CharField(max_length=11, db_index=True)
    code = models.CharField(max_length=128)
    purpose = models.CharField(max_length=20, choices=PURPOSE_CHOICES, default="login")
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "کد یکبار مصرف"
        verbose_name_plural = "کدهای یکبار مصرف"
        ordering = ["-created_at"]

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    @classmethod
    def create_for_mobile(cls, mobile, purpose="login"):
        cls.objects.filter(
            mobile=mobile,
            purpose=purpose,
            is_used=False,
        ).update(is_used=True)

        raw_code = generate_otp()

        otp = cls.objects.create(
            mobile=mobile,
            code=make_password(raw_code),
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=2),
        )

        return otp, raw_code
