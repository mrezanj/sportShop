from django.contrib import admin
from .models import Category, Brand, Product, ProductImage, ProductVariant
from jalali_suite.admin import JalaliDateModelAdmin
from .forms import ProductVariantForm


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    form = ProductVariantForm
    extra = 1


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
        ("محتوا", {"fields": ("description", "ingredients", "usage", "warnings")}),
        (
            "تنظیمات",
            {"fields": ("requires_cold_shipping", "minimum_age", "is_active")},
        ),
    )
