from django.contrib import admin
from .models import Profile, OTPCode, OTPFailedAttempt
from jalali_suite.admin import JalaliDateModelAdmin


@admin.register(Profile)
class ProfileAdmin(JalaliDateModelAdmin):
    list_display = ["mobile", "user", "birth_date", "created_at"]
    search_fields = ["mobile", "user__username"]


@admin.register(OTPCode)
class OTPCodeAdmin(JalaliDateModelAdmin):
    list_display = [
        "mobile",
        "purpose",
        "is_used",
        "attempt_count",
        "expires_at",
        "created_at",
    ]
    list_filter = ["is_used", "purpose"]
    search_fields = ["mobile"]
    readonly_fields = [
        "mobile",
        "code",
        "purpose",
        "expires_at",
        "is_used",
        "attempt_count",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OTPFailedAttempt)
class OTPFailedAttemptAdmin(admin.ModelAdmin):
    list_display = ["mobile", "created_at"]
    search_fields = ["mobile"]
    list_filter = ["created_at"]
    readonly_fields = ["mobile", "created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
