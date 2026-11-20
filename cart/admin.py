
from django.contrib import admin

from .models import Cart, CartItem


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "total_quantity", "subtotal", "created_at", "updated_at"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = ["created_at", "updated_at"]
    inlines = [CartItemInline]


@admin.register(CartItem)
class CartItemAdmin(admin.ModelAdmin):
    list_display = ["id", "cart", "variant", "quantity", "subtotal", "created_at"]
    search_fields = [
        "cart__user__username",
        "variant__product__name_fa",
        "variant__sku",
    ]
    list_filter = ["created_at"]
    readonly_fields = ["created_at", "updated_at"]
