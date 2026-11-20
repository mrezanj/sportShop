
from django.db import models
from django.contrib.auth.models import User
from jalali_suite.models import JalaliDateTimeField

from catalog.models import ProductVariant


class Cart(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="cart",
        verbose_name="کاربر",
    )
    created_at = JalaliDateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین به‌روزرسانی",
    )

    class Meta:
        verbose_name = "سبد خرید"
        verbose_name_plural = "سبدهای خرید"
        ordering = ["-created_at"]

    def __str__(self):
        return f"سبد خرید {self.user.username}"

    @property
    def total_quantity(self):
        return sum(item.quantity for item in self.items.all())

    @property
    def subtotal(self):
        return sum(
            (item.subtotal for item in self.items.select_related("variant")),
            start=0,
        )


class CartItem(models.Model):
    cart = models.ForeignKey(
        Cart,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name="سبد خرید",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="cart_items",
        verbose_name="تنوع محصول",
    )
    quantity = models.PositiveIntegerField(
        default=1,
        verbose_name="تعداد",
    )
    created_at = JalaliDateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ افزودن",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین به‌روزرسانی",
    )

    class Meta:
        verbose_name = "قلم سبد خرید"
        verbose_name_plural = "اقلام سبد خرید"
        constraints = [
            models.UniqueConstraint(
                fields=["cart", "variant"],
                name="unique_cart_variant",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="cart_item_quantity_gte_1",
            ),
        ]
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.variant} × {self.quantity}"

    @property
    def subtotal(self):
        return self.variant.price * self.quantity
