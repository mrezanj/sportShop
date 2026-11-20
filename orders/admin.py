
from django.contrib import admin
from .models import (
    Order,
    OrderItem,
    ShippingMethod,
    ShippingRate,
    StockReservation,
)
from jalali_suite.admin import JalaliDateModelAdmin


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = [
        "product_name",
        "brand_name",
        "variant_label",
        "price",
        "quantity",
        "subtotal",
    ]
    can_delete = False


@admin.register(Order)
class OrderAdmin(JalaliDateModelAdmin):
    list_display = [
        "order_number",
        "user",
        "status",
        "total_amount",
        "province",
        "created_at",
    ]
    list_filter = ["status", "province", "created_at"]
    search_fields = ["order_number", "user__username", "mobile"]
    readonly_fields = [
        "order_number",
        "status",
        "reservation_expires_at",
        "created_at",
        "updated_at",
    ]
    inlines = [OrderItemInline]


@admin.register(StockReservation)
class StockReservationAdmin(admin.ModelAdmin):
    list_display = [
        "order",
        "variant",
        "quantity",
        "status",
        "expires_at",
        "released_at",
        "consumed_at",
    ]
    list_filter = ["status", "expires_at"]
    search_fields = ["order__order_number", "variant__product__name"]
    readonly_fields = [
        "order",
        "variant",
        "quantity",
        "status",
        "created_at",
        "expires_at",
        "released_at",
        "consumed_at",
    ]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "order"]
    list_editable = ["is_active", "order"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ShippingRate)
class ShippingRateAdmin(admin.ModelAdmin):
    list_display = ["method", "province", "cost"]
    list_filter = ["method", "province"]
