
import uuid

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from catalog.models import ProductVariant
from locations.models import City
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

    restricted_province = models.CharField(
        max_length=30,
        choices=PROVINCE_CHOICES,
        blank=True,
        default="",
        verbose_name="استان مجاز",
        help_text="در صورت تعیین، این روش فقط برای همین استان قابل انتخاب است.",
    )
    restricted_city = models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        related_name="restricted_shipping_methods",
        null=True,
        blank=True,
        verbose_name="شهر مجاز",
        help_text="در صورت تعیین، این روش فقط برای همین شهر قابل انتخاب است.",
    )

    class Meta:
        verbose_name = "روش ارسال"
        verbose_name_plural = "روش‌های ارسال"
        ordering = ["order", "id"]

    def clean(self):
        super().clean()

        if (
            self.restricted_city_id
            and self.restricted_province
            and self.restricted_city.province.slug != self.restricted_province
        ):
            raise ValidationError({
                "restricted_city": "شهر انتخاب‌شده متعلق به استان مجاز نیست."
            })

        if self.restricted_city_id and not self.restricted_province:
            self.restricted_province = self.restricted_city.province.slug

    def __str__(self):
        return self.name


class ShippingRate(models.Model):
    method = models.ForeignKey(
        ShippingMethod,
        on_delete=models.CASCADE,
        related_name="rates",
        verbose_name="روش ارسال",
    )
    province = models.CharField(
        max_length=30,
        choices=PROVINCE_CHOICES,
        verbose_name="استان",
    )
    city = models.ForeignKey(
        City,
        on_delete=models.PROTECT,
        related_name="shipping_rates",
        null=True,
        blank=True,
        verbose_name="شهر",
        help_text="خالی باشد، تعرفه برای تمام شهرهای استان اعمال می‌شود.",
    )
    cost = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        validators=[MinValueValidator(0)],
        verbose_name="هزینه پایه ارسال (تومان)",
    )
    included_weight_grams = models.PositiveIntegerField(
        default=1000,
        validators=[MinValueValidator(1)],
        verbose_name="وزن مشمول هزینه پایه (گرم)",
    )
    additional_weight_step_grams = models.PositiveIntegerField(
        default=1000,
        validators=[MinValueValidator(1)],
        verbose_name="هر پله وزن اضافه (گرم)",
    )
    additional_weight_cost = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="هزینه هر پله وزن اضافه (تومان)",
    )
    cold_shipping_cost = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="هزینه اضافه ارسال سرد (تومان)",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "نرخ ارسال"
        verbose_name_plural = "نرخ‌های ارسال"
        ordering = ["method", "province", "city"]
        constraints = [
            models.UniqueConstraint(
                fields=["method", "province"],
                condition=models.Q(city__isnull=True),
                name="unique_shipping_method_province_default",
            ),
            models.UniqueConstraint(
                fields=["method", "province", "city"],
                condition=models.Q(city__isnull=False),
                name="unique_shipping_method_province_city",
            ),
            models.CheckConstraint(
                condition=models.Q(cost__gte=0),
                name="shipping_rate_cost_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(additional_weight_cost__gte=0),
                name="shipping_rate_extra_cost_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(cold_shipping_cost__gte=0),
                name="shipping_rate_cold_cost_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(included_weight_grams__gt=0),
                name="shipping_rate_included_weight_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(additional_weight_step_grams__gt=0),
                name="shipping_rate_weight_step_positive",
            ),
        ]

    def clean(self):
        super().clean()

        if self.city_id and self.city.province.slug != self.province:
            raise ValidationError({
                "city": "شهر انتخاب‌شده متعلق به استان این تعرفه نیست."
            })

    def __str__(self):
        location = self.get_province_display()
        if self.city_id:
            location = f"{location} - {self.city}"
        return f"{self.method.name} - {location} - {self.cost}"


class ShippingConfiguration(models.Model):
    singleton_key = models.PositiveSmallIntegerField(
        default=1,
        unique=True,
        editable=False,
    )
    volumetric_divisor = models.PositiveIntegerField(
        default=5000,
        validators=[MinValueValidator(1)],
        verbose_name="ضریب وزن حجمی",
        help_text="طول × عرض × ارتفاع به سانتی‌متر تقسیم بر این عدد، وزن حجمی را به گرم می‌دهد.",
    )
    free_shipping_threshold = models.DecimalField(
        max_digits=14,
        decimal_places=0,
        default=4000000,
        validators=[MinValueValidator(0)],
        verbose_name="حداقل مبلغ برای ارسال رایگان (تومان)",
    )
    free_packaging_threshold = models.DecimalField(
        max_digits=14,
        decimal_places=0,
        default=5000000,
        validators=[MinValueValidator(0)],
        verbose_name="حداقل مبلغ برای بسته‌بندی رایگان (تومان)",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین بروزرسانی",
    )

    class Meta:
        verbose_name = "تنظیمات ارسال و بسته‌بندی"
        verbose_name_plural = "تنظیمات ارسال و بسته‌بندی"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(volumetric_divisor__gt=0),
                name="shipping_config_divisor_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(free_shipping_threshold__gte=0),
                name="shipping_config_free_shipping_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(free_packaging_threshold__gte=0),
                name="shipping_config_free_packaging_nonnegative",
            ),
        ]

    def save(self, *args, **kwargs):
        self.singleton_key = 1
        super().save(*args, **kwargs)

    def __str__(self):
        return "تنظیمات ارسال و بسته‌بندی"


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
        max_length=20,
        unique=True,
        editable=False,
        verbose_name="شماره سفارش",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="orders",
        verbose_name="کاربر",
    )

    first_name = models.CharField(max_length=100, verbose_name="نام")
    last_name = models.CharField(max_length=100, verbose_name="نام خانوادگی")
    mobile = models.CharField(max_length=11, verbose_name="موبایل")
    province = models.CharField(
        max_length=30,
        choices=PROVINCE_CHOICES,
        verbose_name="استان",
    )
    city = models.CharField(max_length=100, verbose_name="شهر")
    address = models.TextField(verbose_name="آدرس")
    postal_code = models.CharField(
        max_length=10,
        blank=True,
        verbose_name="کد پستی",
    )

    shipping_method = models.ForeignKey(
        ShippingMethod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="used_in_orders",
    )
    shipping_method_name = models.CharField(max_length=50, blank=True)
    shipping_cost = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0,
        verbose_name="هزینه ارسال",
    )
    packaging_cost = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="هزینه بسته‌بندی",
    )

    shipping_actual_weight_grams = models.PositiveIntegerField(
        default=0,
        verbose_name="وزن واقعی سفارش (گرم)",
    )
    shipping_volumetric_weight_grams = models.PositiveIntegerField(
        default=0,
        verbose_name="وزن حجمی سفارش (گرم)",
    )
    shipping_billable_weight_grams = models.PositiveIntegerField(
        default=0,
        verbose_name="وزن قابل محاسبه ارسال (گرم)",
    )
    shipping_is_free = models.BooleanField(default=False, verbose_name="ارسال رایگان")
    packaging_is_free = models.BooleanField(default=False, verbose_name="بسته‌بندی رایگان")
    shipping_calculation_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="جزئیات محاسبات ارسال",
    )

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        verbose_name="جمع کالاها",
    )
    vat_amount = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        verbose_name="مالیات",
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="مبلغ تخفیف",
    )
    pricing_snapshot = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="تصویر ثابت قیمت‌گذاری سفارش",
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        verbose_name="مبلغ نهایی",
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        verbose_name="وضعیت",
    )
    reservation_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="مهلت پایان رزرو موجودی",
    )
    tracking_code = models.CharField(max_length=100, blank=True, verbose_name="کد رهگیری")
    notes = models.TextField(blank=True, verbose_name="یادداشت")
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = JalaliDateTimeField(auto_now=True, verbose_name="تاریخ بروزرسانی")

    class Meta:
        verbose_name = "سفارش"
        verbose_name_plural = "سفارش‌ها"
        ordering = ["-created_at"]
        permissions = [
            ("can_manage_order_status", "Can manage order status"),
            ("can_manage_order_shipping_cost", "Can manage order shipping cost"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(shipping_cost__gte=0),
                name="order_shipping_cost_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(packaging_cost__gte=0),
                name="order_packaging_cost_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_amount__gte=0),
                name="order_discount_nonnegative",
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
    note = models.TextField(blank=True, verbose_name="توضیحات")
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="زمان تغییر")

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
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    product_name = models.CharField(max_length=200, verbose_name="نام محصول")
    product_slug = models.CharField(max_length=200)
    brand_name = models.CharField(max_length=100, verbose_name="برند")
    variant_label = models.CharField(max_length=200, verbose_name="تنوع")
    image_url = models.CharField(max_length=500, blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="قیمت واحد")
    quantity = models.PositiveIntegerField(verbose_name="تعداد")
    subtotal = models.DecimalField(max_digits=12, decimal_places=0, verbose_name="جمع قبل از تخفیف")
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="تخفیف قلم سفارش",
    )

    shipping_weight_grams = models.PositiveIntegerField(default=0, verbose_name="وزن ارسال واحد (گرم)")
    shipping_length_cm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="طول ارسال (سانتی‌متر)")
    shipping_width_cm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="عرض ارسال (سانتی‌متر)")
    shipping_height_cm = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, verbose_name="ارتفاع ارسال (سانتی‌متر)")
    requires_cold_shipping = models.BooleanField(default=False, verbose_name="نیازمند ارسال سرد")
    requires_special_packaging = models.BooleanField(default=False, verbose_name="نیازمند بسته‌بندی ویژه")
    special_packaging_cost = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="هزینه بسته‌بندی ویژه واحد",
    )

    class Meta:
        verbose_name = "آیتم سفارش"
        verbose_name_plural = "آیتم‌های سفارش"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(special_packaging_cost__gte=0),
                name="order_item_packaging_cost_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(discount_amount__gte=0)
                    & models.Q(discount_amount__lte=models.F("subtotal"))
                ),
                name="order_item_discount_within_subtotal",
            ),
        ]

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
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان ایجاد")
    expires_at = models.DateTimeField(verbose_name="زمان انقضا")
    released_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان آزادسازی")
    consumed_at = models.DateTimeField(null=True, blank=True, verbose_name="زمان مصرف")

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
        return f"{self.order.order_number} - {self.variant} - {self.quantity}"



class CheckoutPriceQuote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="checkout_price_quotes",
    )
    payload = models.JSONField(verbose_name="جزئیات قیمت تأییدشده")
    expires_at = models.DateTimeField(verbose_name="زمان انقضای پیش‌نمایش")
    consumed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان استفاده",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "پیش‌نمایش قیمت تسویه"
        verbose_name_plural = "پیش‌نمایش‌های قیمت تسویه"
        indexes = [
            models.Index(fields=["user", "expires_at"], name="checkout_quote_user_exp_idx"),
        ]

    def __str__(self):
        return f"{self.user_id} - {self.id}"
