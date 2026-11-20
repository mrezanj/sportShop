from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from catalog.models import ProductVariant
from jalali_suite.models import JalaliDateTimeField

PROVINCE_CHOICES = [
    ("tehran", "تهران"),
    ("alborz", "البرز"),
    ("ardabil", "اردبیل"),
    ("bushehr", "بوشهر"),
    ("chaharmahal", "چهارمحال و بختیاری"),
    ("east-azerbaijan", "آذربایجان شرقی"),
    ("isfahan", "اصفهان"),
    ("fars", "فارس"),
    ("gilan", "گیلان"),
    ("golestan", "گلستان"),
    ("hamedan", "همدان"),
    ("hormozgan", "هرمزگان"),
    ("ilam", "ایلام"),
    ("kerman", "کرمان"),
    ("kermanshah", "کرمانشاه"),
    ("khuzestan", "خوزستان"),
    ("kohgiluyeh", "کهگیلویه و بویراحمد"),
    ("kurdistan", "کردستان"),
    ("lorestan", "لرستان"),
    ("markazi", "مرکزی"),
    ("mazandaran", "مازندران"),
    ("north-khorasan", "خراسان شمالی"),
    ("qazvin", "قزوین"),
    ("qom", "قم"),
    ("razavi-khorasan", "خراسان رضوی"),
    ("semnan", "سمنان"),
    ("sistan", "سیستان و بلوچستان"),
    ("south-khorasan", "خراسان جنوبی"),
    ("west-azerbaijan", "آذربایجان غربی"),
    ("yazd", "یزد"),
    ("zanjan", "زنجان"),
]


class ShippingMethod(models.Model):
    name = models.CharField(max_length=50, verbose_name="نام")
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True, verbose_name="توضیحات")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب")

    class Meta:
        verbose_name = "روش ارسال"
        verbose_name_plural = "روش‌های ارسال"
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class ShippingRate(models.Model):
    method = models.ForeignKey(
        ShippingMethod, on_delete=models.CASCADE, related_name="rates"
    )
    province = models.CharField(
        max_length=30, choices=PROVINCE_CHOICES, verbose_name="استان"
    )
    cost = models.DecimalField(
        max_digits=10, decimal_places=0, verbose_name="هزینه (تومان)"
    )

    class Meta:
        verbose_name = "نرخ ارسال"
        verbose_name_plural = "نرخ‌های ارسال"
        unique_together = ["method", "province"]

    def __str__(self):
        return f"{self.method.name} - {self.get_province_display()} - {self.cost}"


class Order(models.Model):
    STATUS_CHOICES = [
        ("pending", "در انتظار پرداخت"),
        ("paid", "پرداخت شده"),
        ("processing", "در حال پردازش"),
        ("shipped", "ارسال شده"),
        ("delivered", "تحویل شده"),
        ("cancelled", "لغو شده"),
    ]

    order_number = models.CharField(
        max_length=20, unique=True, editable=False, verbose_name="شماره سفارش"
    )
    user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="orders", verbose_name="کاربر"
    )

    # Shipping info
    first_name = models.CharField(max_length=100, verbose_name="نام")
    last_name = models.CharField(max_length=100, verbose_name="نام خانوادگی")
    mobile = models.CharField(max_length=11, verbose_name="موبایل")
    province = models.CharField(
        max_length=30, choices=PROVINCE_CHOICES, verbose_name="استان"
    )
    city = models.CharField(max_length=100, verbose_name="شهر")
    address = models.TextField(verbose_name="آدرس")
    postal_code = models.CharField(max_length=10, blank=True, verbose_name="کد پستی")

    # Shipping
    shipping_method = models.ForeignKey(
        ShippingMethod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="used_in_orders",
    )
    shipping_method_name = models.CharField(max_length=50, blank=True)
    shipping_cost = models.DecimalField(
        max_digits=12, decimal_places=0, default=0, verbose_name="هزینه ارسال"
    )

    # Financial
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=0, verbose_name="جمع کالاها"
    )
    vat_amount = models.DecimalField(
        max_digits=12, decimal_places=0, verbose_name="مالیات"
    )
    total_amount = models.DecimalField(
        max_digits=12, decimal_places=0, verbose_name="مبلغ نهایی"
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="وضعیت"
    )
    reservation_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="مهلت پایان رزرو موجودی",
    )
    tracking_code = models.CharField(
        max_length=100, blank=True, verbose_name="کد رهگیری"
    )
    notes = models.TextField(blank=True, verbose_name="یادداشت")
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = JalaliDateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        ordering = ["-created_at"]
        permissions = [
            (
                "can_manage_order_status",
                "Can manage order status",
            ),
        ]

    def __str__(self):
        return self.order_number

    def save(self, *args, **kwargs):
        if not self.order_number:
            now = timezone.now()
            prefix = f'ORD-{now.strftime("%y%m%d")}'
            last = (
                Order.objects.filter(order_number__startswith=prefix)
                .order_by("-id")
                .first()
            )
            if last:
                try:
                    n = int(last.order_number.split("-")[-1]) + 1
                except (ValueError, IndexError):
                    n = 1
            else:
                n = 1
            self.order_number = f"{prefix}-{n:04d}"
        super().save(*args, **kwargs)


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_history",
        verbose_name="سفارش",
    )
    old_status = models.CharField(
        max_length=20,
        choices=Order.STATUS_CHOICES,
        blank=True,
        default="",
        verbose_name="وضعیت قبلی",
    )
    new_status = models.CharField(
        max_length=20,
        choices=Order.STATUS_CHOICES,
        verbose_name="وضعیت جدید",
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_changes",
        verbose_name="تغییردهنده",
    )
    note = models.TextField(
        blank=True,
        verbose_name="توضیحات",
    )
    created_at = JalaliDateTimeField(
        auto_now_add=True,
        verbose_name="زمان تغییر",
    )

    class Meta:
        verbose_name = "تاریخچه وضعیت سفارش"
        verbose_name_plural = "تاریخچه وضعیت سفارش‌ها"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["order", "created_at"],
                name="order_status_history_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.order.order_number}: "
            f"{self.old_status or '—'} → {self.new_status}"
        )


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.SET_NULL, null=True, blank=True
    )
    product_name = models.CharField(max_length=200, verbose_name="نام محصول")
    product_slug = models.CharField(max_length=200)
    brand_name = models.CharField(max_length=100, verbose_name="برند")
    variant_label = models.CharField(max_length=200, verbose_name="تنوع")
    image_url = models.CharField(max_length=500, blank=True)
    price = models.DecimalField(
        max_digits=12, decimal_places=0, verbose_name="قیمت واحد"
    )
    quantity = models.PositiveIntegerField(verbose_name="تعداد")
    subtotal = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="جمع")

    class Meta:
        verbose_name = "آیتم سفارش"
        verbose_name_plural = "آیتم‌های سفارش"

    def __str__(self):
        return f"{self.order.order_number} - {self.product_name}"


class StockReservation(models.Model):
    STATUS_CHOICES = [
        ("active", "فعال"),
        ("consumed", "مصرف‌شده"),
        ("released", "آزادشده"),
        ("expired", "منقضی‌شده"),
    ]

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="stock_reservations",
        verbose_name="سفارش",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="stock_reservations",
        verbose_name="تنوع محصول",
    )
    quantity = models.PositiveIntegerField(verbose_name="تعداد رزروشده")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="active",
        verbose_name="وضعیت",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان ایجاد",
    )
    expires_at = models.DateTimeField(verbose_name="زمان انقضا")
    released_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان آزادسازی",
    )
    consumed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان مصرف",
    )

    class Meta:
        verbose_name = "رزرو موجودی"
        verbose_name_plural = "رزروهای موجودی"
        constraints = [
            models.UniqueConstraint(
                fields=["order", "variant"],
                name="unique_order_variant_reservation",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="stock_reservation_quantity_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "expires_at"],
                name="reservation_status_exp_idx",
            ),
        ]

    def __str__(self):
        return f"{self.order.order_number} - " f"{self.variant} - {self.quantity}"
