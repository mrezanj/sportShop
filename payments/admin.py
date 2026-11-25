from django.contrib import admin
from .models import Payment, Refund, RefundHistory
from jalali_suite.admin import JalaliDateModelAdmin


@admin.register(Payment)
class PaymentAdmin(JalaliDateModelAdmin):
    list_display = [
        "id",
        "order",
        "gateway",
        "amount",
        "status",
        "ref_id",
        "created_at",
    ]
    list_filter = ["status", "gateway", "created_at"]
    search_fields = ["order__order_number", "authority", "ref_id"]
    readonly_fields = [
        "order",
        "gateway",
        "amount",
        "status",
        "authority",
        "ref_id",
        "gateway_response",
        "created_at",
        "paid_at",
    ]
    ordering = ["-created_at"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



class RefundHistoryInline(admin.TabularInline):
    model = RefundHistory
    extra = 0
    can_delete = False
    fields = ("old_status", "new_status", "changed_by", "provider_reference", "note", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Refund)
class RefundAdmin(JalaliDateModelAdmin):
    list_display = ("id", "return_request", "payment", "amount", "status", "provider_reference", "created_at", "completed_at")
    list_filter = ("status", "created_at")
    search_fields = ("return_request__order__order_number", "provider_reference", "idempotency_key")
    readonly_fields = (
        "return_request", "payment", "amount", "status", "idempotency_key",
        "provider_reference", "provider_response", "requested_by", "processed_by",
        "created_at", "updated_at", "completed_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Refund state transitions must go through the permission-checked API/service.
        # Django Admin is intentionally read-only, even for refund operators.
        return False

    def has_delete_permission(self, request, obj=None):
        return False
