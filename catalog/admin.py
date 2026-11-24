
from django.contrib import admin

from jalali_suite.admin import JalaliDateModelAdmin

from .forms import ProductVariantForm
from .models import (
    Brand, Category, Product, ProductImage, ProductVariant,
    ProductVariantPriceHistory,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.StackedInline):
    model = ProductVariant
    form = ProductVariantForm
    extra = 1
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

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
