from django.contrib import admin, messages
from django.db import transaction

from jalali_suite.admin import JalaliDateModelAdmin

from .models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    ShippingMethod,
    ShippingRate,
    StockReservation,
)
from .services import (
    InvalidOrderStatusTransition,
    transition_order_status,
)


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

    def has_add_permission(self, request, obj=None):
        return False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    can_delete = False

    fields = [
        "old_status",
        "new_status",
        "changed_by",
        "note",
        "created_at",
    ]
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


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

    inlines = [
        OrderItemInline,
        OrderStatusHistoryInline,
    ]

    actions = [
        "mark_processing",
        "mark_shipped",
        "mark_delivered",
    ]

    def has_manage_order_status_permission(self, request):
        return request.user.has_perm("orders.can_manage_order_status")

    def _transition_selected_orders(
        self,
        request,
        queryset,
        new_status,
        note,
    ):
        success_count = 0
        skipped_count = 0

        order_ids = list(queryset.values_list("pk", flat=True))

        for order_id in order_ids:
            try:
                with transaction.atomic():
                    order = Order.objects.select_for_update().get(pk=order_id)

                    changed = transition_order_status(
                        order=order,
                        new_status=new_status,
                        changed_by=request.user,
                        note=note,
                    )

                    if changed:
                        success_count += 1
                    else:
                        skipped_count += 1

            except (InvalidOrderStatusTransition, Order.DoesNotExist):
                skipped_count += 1

        if success_count:
            self.message_user(
                request,
                f"وضعیت {success_count} سفارش با موفقیت تغییر کرد.",
                messages.SUCCESS,
            )

        if skipped_count:
            self.message_user(
                request,
                f"{skipped_count} سفارش به دلیل وضعیت فعلی یا حذف شدن، تغییر نکرد.",
                messages.WARNING,
            )

    @admin.action(
        description="انتقال سفارش‌های پرداخت‌شده به در حال پردازش",
        permissions=["manage_order_status"],
    )
    def mark_processing(self, request, queryset):
        self._transition_selected_orders(
            request,
            queryset,
            "processing",
            "تغییر وضعیت به در حال پردازش از پنل مدیریت.",
        )

    @admin.action(
        description="انتقال سفارش‌های در حال پردازش به ارسال‌شده",
        permissions=["manage_order_status"],
    )
    def mark_shipped(self, request, queryset):
        self._transition_selected_orders(
            request,
            queryset,
            "shipped",
            "تغییر وضعیت به ارسال‌شده از پنل مدیریت.",
        )

    @admin.action(
        description="انتقال سفارش‌های ارسال‌شده به تحویل‌شده",
        permissions=["manage_order_status"],
    )
    def mark_delivered(self, request, queryset):
        self._transition_selected_orders(
            request,
            queryset,
            "delivered",
            "تغییر وضعیت به تحویل‌شده از پنل مدیریت.",
        )


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
