from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta
import random
import string
from jalali_suite.models import JalaliDateTimeField

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))


class Profile(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='profile'
    )
    mobile = models.CharField(max_length=11, unique=True)
    birth_date = models.DateField(null=True, blank=True, verbose_name='تاریخ تولد')
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = 'پروفایل'
        verbose_name_plural = 'پروفایل‌ها'

    def __str__(self):
        return self.mobile


class OTPCode(models.Model):
    PURPOSE_CHOICES = [
        ('login', 'ورود'),
        ('register', 'ثبت‌نام'),
    ]
    mobile = models.CharField(max_length=11, db_index=True)
    code = models.CharField(max_length=6)
    purpose = models.CharField(
        max_length=20, choices=PURPOSE_CHOICES, default='login'
    )
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = 'کد یکبار مصرف'
        verbose_name_plural = 'کدهای یکبار مصرف'
        ordering = ['-created_at']

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    @classmethod
    def create_for_mobile(cls, mobile, purpose='login'):
        # همه کدهای قبلی همین موبایل را منقضی کن
        cls.objects.filter(mobile=mobile, is_used=False).update(is_used=True)
        return cls.objects.create(
            mobile=mobile,
            code=generate_otp(),
            purpose=purpose,
            expires_at=timezone.now() + timedelta(minutes=2),
        )