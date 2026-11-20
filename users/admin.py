from django.contrib import admin
from .models import Profile, OTPCode
from jalali_suite.admin import JalaliDateModelAdmin


@admin.register(Profile)
class ProfileAdmin(JalaliDateModelAdmin):
    list_display = ['mobile', 'user', 'birth_date', 'created_at']
    search_fields = ['mobile', 'user__username']


@admin.register(OTPCode)
class OTPCodeAdmin(JalaliDateModelAdmin):
    list_display = ['mobile', 'code', 'purpose', 'is_used', 'expires_at', 'created_at']
    list_filter = ['is_used', 'purpose']
    search_fields = ['mobile']