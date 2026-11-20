from django.contrib import admin
from .models import Order, OrderItem, ShippingMethod, ShippingRate
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
class OrderAdmin(
    JalaliDateModelAdmin
):  
    list_display = [
        "order_number",
        "user",
        "status",
        "total_amount",
        "province",
        "created_at",  # created_at حالا به صورت خودکار شمسی نمایش داده می‌شود
    ]
    list_filter = ["status", "province", "created_at"]
    search_fields = ["order_number", "user__username", "mobile"]
    readonly_fields = [
        "order_number",
        "created_at",
        "updated_at",
    ]  # این فیلدها هم در صفحه ویرایش شمسی می‌شوند
    inlines = [OrderItemInline]
    list_editable = ["status"]


@admin.register(ShippingMethod)
class ShippingMethodAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "order"]
    list_editable = ["is_active", "order"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(ShippingRate)
class ShippingRateAdmin(admin.ModelAdmin):
    list_display = ["method", "province", "cost"]
    list_filter = ["method", "province"]
