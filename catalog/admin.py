
from django.contrib import admin

from jalali_suite.admin import JalaliDateModelAdmin

from .forms import ProductVariantForm
from .models import (
    Brand, Category, Product, ProductImage, ProductVariant,
    ProductVariantPriceHistory,
    DiscountCampaign,
    DiscountRedemption,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.StackedInline):
    model = ProductVariant
    form = ProductVariantForm
    extra = 1

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser and not request.user.has_perm(
            "catalog.can_manage_product_prices"
        ):
            readonly.append("price")
        return readonly
    fieldsets = (
        (
            "مشخصات تنوع محصول",
            {
                "fields": (
                    ("flavor", "weight", "servings"),
                    ("size", "color", "sku"),
                    "attributes",
                    ("price", "is_active"),
                )
            },
        ),
        (
            "اطلاعات حمل و ابعاد بسته",
            {
                "fields": (
                    "shipping_weight_grams",
                    ("shipping_length_cm", "shipping_width_cm", "shipping_height_cm"),
                ),
                "description": "وزن و ابعاد واقعی بسته آماده ارسال را وارد کنید. هر سه بُعد باید با هم تکمیل شوند.",
            },
        ),
        (
            "بسته‌بندی ویژه",
            {
                "fields": (
                    "requires_special_packaging",
                    "special_packaging_cost",
                ),
                "description": "هزینه بسته‌بندی ویژه برای هر واحد محصول به تومان ثبت می‌شود.",
            },
        ),
    )


@admin.register(Category)
class CategoryAdmin(JalaliDateModelAdmin):
    list_display = ["name", "parent", "is_active", "image", "created_at"]
    list_filter = ["is_active", "parent"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}
    fields = ["name", "slug", "parent", "image", "is_active"]


@admin.register(Brand)
class BrandAdmin(JalaliDateModelAdmin):
    list_display = ["name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(JalaliDateModelAdmin):
    list_display = ["name_fa", "brand", "category", "is_active", "created_at"]
    list_filter = ["is_active", "brand", "category", "requires_cold_shipping"]
    search_fields = ["name_fa", "name_en", "brand__name"]
    prepopulated_fields = {"slug": ("name_en",)}
    inlines = [ProductImageInline, ProductVariantInline]

    def save_formset(self, request, form, formset, change):
        if formset.model is ProductVariant:
            price_changes = []
            for variant_form in formset.forms:
                if not variant_form.has_changed() or variant_form.cleaned_data.get("DELETE"):
                    continue
                if "price" not in variant_form.changed_data:
                    continue
                instance = variant_form.instance
                old_price = (
                    ProductVariant.objects.filter(pk=instance.pk)
                    .values_list("price", flat=True)
                    .first()
                    if instance.pk else None
                )
                new_price = variant_form.cleaned_data.get("price")
                if old_price != new_price:
                    price_changes.append((instance, old_price, new_price))
            super().save_formset(request, form, formset, change)
            for instance, old_price, new_price in price_changes:
                ProductVariantPriceHistory.objects.create(
                    variant=instance,
                    sku=instance.sku,
                    product_name=instance.product.name_fa,
                    old_price=old_price,
                    new_price=new_price,
                    change_type="initial" if old_price is None else "manual",
                    changed_by=request.user,
                    note="تغییر قیمت از فرم مدیریت محصول",
                )
            return
        super().save_formset(request, form, formset, change)

    fieldsets = (
        (
            "اطلاعات اصلی",
            {"fields": ("name_fa", "name_en", "slug", "brand", "category")},
        ),
        (
            "محتوا و اطلاعات علمی",
            {
                "fields": (
                    "description",
                    "ingredients",
                    "usage",
                    "warnings",
                    "contraindications",
                    "medical_advice",
                    "consumption_goals",
                )
            },
        ),
        (
            "مجوز و اصالت",
            {"fields": ("license_id", "authenticity_code", "license_details")},
        ),
        (
            "تنظیمات",
            {"fields": ("requires_cold_shipping", "minimum_age", "is_active")},
        ),
    )



@admin.register(ProductVariantPriceHistory)
class ProductVariantPriceHistoryAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "product_name",
        "old_price",
        "new_price",
        "change_type",
        "changed_by",
        "created_at",
    )
    list_filter = ("change_type", "created_at")
    search_fields = ("sku", "product_name", "note", "changed_by__username")
    readonly_fields = (
        "variant",
        "sku",
        "product_name",
        "old_price",
        "new_price",
        "change_type",
        "changed_by",
        "note",
        "created_at",
    )

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser or request.user.has_perm(
            "catalog.can_manage_product_prices"
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(DiscountCampaign)
class DiscountCampaignAdmin(JalaliDateModelAdmin):
    def _allowed(self, request):
        return request.user.is_superuser or (
            request.user.is_staff
            and request.user.has_perm("catalog.can_manage_discounts")
        )

    def has_module_permission(self, request):
        return self._allowed(request)

    def has_view_permission(self, request, obj=None):
        return self._allowed(request)

    def has_add_permission(self, request):
        return self._allowed(request)

    def has_change_permission(self, request, obj=None):
        return self._allowed(request)

    def has_delete_permission(self, request, obj=None):
        return False

    list_display = (
        "name", "scope", "discount_type", "value", "code",
        "starts_at", "ends_at", "priority", "usage_count", "is_active",
    )
    list_filter = ("scope", "discount_type", "is_active", "first_purchase_only", "is_stackable")
    search_fields = ("name", "code")
    readonly_fields = ("usage_count", "created_at", "updated_at")
    fieldsets = (
        ("تعریف تخفیف", {
            "fields": ("name", "scope", "product", "category", "brand",
                       "discount_type", "value", "maximum_discount_amount",
                       "minimum_order_amount", "code")
        }),
        ("زمان‌بندی و ترکیب", {
            "fields": ("starts_at", "ends_at", "priority", "is_stackable",
                       "first_purchase_only", "is_active")
        }),
        ("محدودیت استفاده", {
            "fields": ("max_uses", "per_user_limit", "usage_count")
        }),
        ("سوابق", {"fields": ("created_at", "updated_at")}),
    )

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)


@admin.register(DiscountRedemption)
class DiscountRedemptionAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser or (
            request.user.is_staff
            and request.user.has_perm("catalog.can_manage_discounts")
        )

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)
    list_display = ("campaign", "order", "user", "discount_amount", "code_used", "status", "created_at")
    list_filter = ("campaign", "created_at")
    search_fields = ("campaign__name", "code_used", "order__order_number", "user__username")
    readonly_fields = ("campaign", "order", "user", "discount_amount", "code_used", "status", "created_at")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
