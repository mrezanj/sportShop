
from django.contrib import admin, messages
from django.db import transaction

from jalali_suite.admin import JalaliDateModelAdmin

from .models import (
    CheckoutPriceQuote,
    Order,
    OrderItem,
    OrderStatusHistory,
    ShippingMethod,
    ShippingRate,
    ShippingConfiguration,
    StockReservation,
    OrderDiscrepancy,
    ReturnRequest,
    ReturnRequestItem,
    ReturnRequestHistory,
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
        "discount_amount",
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
        "city",
        "shipping_method_name",
        "shipping_cost",
        "created_at",
    ]
    list_filter = [
        "status",
        "province",
        "shipping_method",
        "shipping_is_free",
        "packaging_is_free",
        "created_at",
    ]
    search_fields = [
        "order_number",
        "user__username",
        "mobile",
        "city",
        "tracking_code",
    ]

    readonly_fields = [
        "order_number",
        "status",
        "reservation_expires_at",
        "created_at",
        "updated_at",
        "shipping_calculation_snapshot",
        "pricing_snapshot",
        "subtotal",
        "vat_amount",
        "discount_amount",
        "total_amount",
        "shipping_actual_weight_grams",
        "shipping_volumetric_weight_grams",
        "shipping_billable_weight_grams",
        "shipping_is_free",
        "packaging_is_free",
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

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.has_perm("orders.can_manage_order_shipping_cost"):
            readonly.append("shipping_cost")
        return readonly

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
    search_fields = [
        "order__order_number",
        "variant__product__name",
    ]

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
    list_display = [
        "name",
        "slug",
        "restricted_province",
        "restricted_city",
        "is_active",
        "order",
    ]
    list_filter = [
        "is_active",
        "restricted_province",
    ]
    search_fields = [
        "name",
        "slug",
        "restricted_city__name",
        "restricted_city__county_name",
    ]
    list_select_related = [
        "restricted_city",
        "restricted_city__province",
    ]
    list_editable = [
        "is_active",
        "order",
    ]
    raw_id_fields = [
        "restricted_city",
    ]
    prepopulated_fields = {
        "slug": ("name",),
    }


@admin.register(ShippingRate)
class ShippingRateAdmin(admin.ModelAdmin):
    list_display = [
        "method",
        "province",
        "city",
        "cost",
        "included_weight_grams",
        "additional_weight_step_grams",
        "additional_weight_cost",
        "cold_shipping_cost",
        "is_active",
    ]
    list_filter = [
        "method",
        "province",
        "is_active",
        "city__province",
    ]
    search_fields = [
        "method__name",
        "city__name",
        "city__county_name",
        "city__code",
    ]
    list_select_related = [
        "method",
        "city",
        "city__province",
    ]
    raw_id_fields = [
        "city",
    ]


@admin.register(ShippingConfiguration)
class ShippingConfigurationAdmin(admin.ModelAdmin):
    list_display = [
        "volumetric_divisor",
        "free_shipping_threshold",
        "free_packaging_threshold",
        "is_active",
        "updated_at",
    ]

    readonly_fields = [
        "singleton_key",
        "updated_at",
    ]

    fieldsets = [
        (
            "محاسبه وزن حجمی",
            {
                "fields": [
                    "volumetric_divisor",
                ],
            },
        ),
        (
            "آستانه‌های رایگان",
            {
                "fields": [
                    "free_shipping_threshold",
                    "free_packaging_threshold",
                ],
            },
        ),
        (
            "وضعیت تنظیمات",
            {
                "fields": [
                    "is_active",
                    "singleton_key",
                    "updated_at",
                ],
            },
        ),
    ]

    def has_add_permission(self, request):
        if ShippingConfiguration.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False



@admin.register(CheckoutPriceQuote)
class CheckoutPriceQuoteAdmin(admin.ModelAdmin):
    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    list_display = ("id", "user", "expires_at", "consumed_at", "created_at")
    list_filter = ("expires_at", "consumed_at")
    search_fields = ("id", "user__username")
    readonly_fields = ("id", "user", "payload", "expires_at", "consumed_at", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False



class ReturnRequestItemInline(admin.TabularInline):
    model = ReturnRequestItem
    extra = 0
    readonly_fields = ("order_item", "quantity")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(OrderDiscrepancy)
class OrderDiscrepancyAdmin(admin.ModelAdmin):
    list_display = ("order", "status", "opened_by", "created_at", "resolved_by", "resolved_at")
    list_filter = ("status", "created_at")
    search_fields = ("order__order_number", "reason", "resolution")
    readonly_fields = ("order", "status", "reason", "previous_order_status", "opened_by", "created_at", "resolved_by", "resolved_at", "resolution")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("orders.can_manage_order_discrepancies")

    def has_delete_permission(self, request, obj=None):
        return False


class ReturnRequestHistoryInline(admin.TabularInline):
    model = ReturnRequestHistory
    extra = 0
    can_delete = False
    fields = ("old_status", "new_status", "changed_by", "note", "created_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(ReturnRequest)
class ReturnRequestAdmin(admin.ModelAdmin):
    list_display = ("order", "user", "status", "created_at", "reviewed_by")
    list_filter = ("status", "created_at")
    search_fields = ("order__order_number", "user__username", "reason")
    readonly_fields = ("order", "user", "reason", "status", "staff_note", "reviewed_by", "created_at", "updated_at")
    inlines = [ReturnRequestItemInline, ReturnRequestHistoryInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("orders.can_review_return_requests")

    def has_delete_permission(self, request, obj=None):
        return False
