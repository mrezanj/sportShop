from django.contrib import admin
from .models import Payment
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
