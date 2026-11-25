
import uuid
import hashlib
import json

from django.conf import settings
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from jalali_suite.models import JalaliDateTimeField


class Category(models.Model):
    """دسته‌بندی محصولات مثل: پروتئین وی، کراتین، پوشاک ورزشی"""

    name = models.CharField(max_length=100, verbose_name="نام دسته")
    slug = models.SlugField(max_length=100, unique=True, verbose_name="اسلاگ")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="children",
        verbose_name="دسته والد",
    )
    image = models.ImageField(
        upload_to="categories/", null=True, blank=True, verbose_name="عکس دسته"
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "دسته‌بندی"
        verbose_name_plural = "دسته‌بندی‌ها"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Brand(models.Model):
    """برندها مثل: Optimum Nutrition, Dymatize, ..."""

    name = models.CharField(max_length=100, unique=True, verbose_name="نام برند")
    slug = models.SlugField(max_length=100, unique=True)
    logo = models.ImageField(
        upload_to="brands/logos/", null=True, blank=True, verbose_name="لوگو"
    )
    description = models.TextField(blank=True, verbose_name="توضیحات")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "برند"
        verbose_name_plural = "برندها"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    """محصول اصلی - اطلاعات ثابت هر محصول"""

    name_fa = models.CharField(max_length=200, verbose_name="نام فارسی")
    name_en = models.CharField(max_length=200, blank=True, verbose_name="نام انگلیسی")
    slug = models.SlugField(max_length=200, unique=True, verbose_name="اسلاگ")
    brand = models.ForeignKey(
        Brand, on_delete=models.PROTECT, related_name="products", verbose_name="برند"
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="products",
        verbose_name="دسته‌بندی",
    )
    description = models.TextField(verbose_name="توضیحات کامل")
    ingredients = models.TextField(blank=True, verbose_name="مواد تشکیل‌دهنده")
    usage = models.TextField(blank=True, verbose_name="روش مصرف")
    warnings = models.TextField(blank=True, verbose_name="هشدارها")
    contraindications = models.TextField(
        blank=True,
        verbose_name="موارد منع مصرف",
    )
    medical_advice = models.TextField(
        blank=True,
        verbose_name="توصیه پزشکی",
    )
    license_id = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="شناسه مجوز",
    )
    authenticity_code = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="شناسه اصالت",
    )
    license_details = models.TextField(
        blank=True,
        verbose_name="اطلاعات تکمیلی مجوز و اصالت",
    )
    consumption_goals = models.JSONField(
        default=list,
        blank=True,
        verbose_name="اهداف مصرف",
        help_text="فهرستی از اهداف مصرف؛ مانند افزایش حجم، کاهش وزن یا سلامت عمومی.",
    )
    requires_cold_shipping = models.BooleanField(
        default=False, verbose_name="نیاز به ارسال سرد"
    )
    minimum_age = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        verbose_name="حداقل سن خریدار",
        help_text="در صورت خالی بودن، خرید محصول محدودیت سنی ندارد.",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "محصول"
        verbose_name_plural = "محصولات"
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if not isinstance(self.consumption_goals, list) or any(
            not isinstance(goal, str) or not goal.strip()
            for goal in self.consumption_goals
        ):
            raise ValidationError(
                {"consumption_goals": "اهداف مصرف باید فهرستی از متن‌های غیرخالی باشد."}
            )

    def __str__(self):
        return self.name_fa


class ProductImage(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="images", verbose_name="محصول"
    )
    image = models.ImageField(upload_to="products/", verbose_name="عکس")
    alt_text = models.CharField(max_length=200, blank=True)
    is_primary = models.BooleanField(default=False, verbose_name="عکس اصلی")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب")

    class Meta:
        verbose_name = "عکس محصول"
        verbose_name_plural = "عکس‌های محصول"
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_primary=True),
                name="unique_primary_image_per_product",
            ),
        ]

    def save(self, *args, **kwargs):
        # Serialize primary-image changes per product and preserve the
        # database-level one-primary-image invariant.
        from django.db import transaction

        with transaction.atomic():
            Product.objects.select_for_update().get(pk=self.product_id)
            self._save_with_primary_lock(*args, **kwargs)

    def _save_with_primary_lock(self, *args, **kwargs):
        # If this image is being set as primary, unset the others
        if self.is_primary:
            ProductImage.objects.filter(product=self.product, is_primary=True).exclude(
                pk=self.pk
            ).update(is_primary=False)

        # Auto-primary if this is the only image for the product
        if not self.is_primary:
            other_exists = (
                ProductImage.objects.filter(product=self.product)
                .exclude(pk=self.pk)
                .exists()
            )
            if not other_exists:
                self.is_primary = True

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.db import transaction

        with transaction.atomic():
            Product.objects.select_for_update().get(pk=self.product_id)
            product = self.product
            was_primary = self.is_primary
            super().delete(*args, **kwargs)
            if was_primary:
                first_remaining = ProductImage.objects.filter(
                    product=product
                ).order_by("order", "id").first()
                if first_remaining and not first_remaining.is_primary:
                    ProductImage.objects.filter(pk=first_remaining.pk).update(
                        is_primary=True
                    )

    def __str__(self):
        return self.alt_text or self.product.name_fa


class ProductVariant(models.Model):
    """تنوع محصول: طعم، وزن، تعداد سروینگ و ... + موجودی و قیمت"""

    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variants", verbose_name="محصول"
    )
    flavor = models.CharField(max_length=100, blank=True, verbose_name="طعم")
    weight = models.CharField(max_length=50, blank=True, verbose_name="وزن نمایشی")
    servings = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="تعداد سروینگ"
    )
    size = models.CharField(max_length=20, blank=True, verbose_name="سایز (برای پوشاک)")
    color = models.CharField(max_length=50, blank=True, verbose_name="رنگ")
    attributes = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="ویژگی‌های سفارشی",
        help_text="ویژگی‌های اختصاصی این تنوع به‌صورت شیء JSON؛ مثال: {\"serving_type\": \"کپسول\", \"material\": \"پلی‌استر\"}.",
    )
    sku = models.CharField(
        max_length=100, unique=True, blank=True, verbose_name="کد انبار (SKU)"
    )
    variant_fingerprint = models.CharField(
        max_length=64, blank=True, default="", editable=False,
        verbose_name="شناسه ترکیب ویژگی‌های تنوع",
    )

    # Physical shipping specifications
    shipping_weight_grams = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        verbose_name="وزن قابل ارسال (گرم)",
        help_text="وزن واقعی بسته‌بندی‌شده برای ارسال، به گرم.",
    )
    shipping_length_cm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="طول بسته (سانتی‌متر)",
    )
    shipping_width_cm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="عرض بسته (سانتی‌متر)",
    )
    shipping_height_cm = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        verbose_name="ارتفاع بسته (سانتی‌متر)",
    )

    # Special packaging
    requires_special_packaging = models.BooleanField(
        default=False,
        verbose_name="نیازمند بسته‌بندی ویژه",
    )
    special_packaging_cost = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="هزینه بسته‌بندی ویژه هر واحد (تومان)",
    )

    price = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        validators=[MinValueValidator(Decimal("1"))],
        verbose_name="قیمت (تومان)",
    )
    stock = models.PositiveIntegerField(default=0, verbose_name="موجودی")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "تنوع محصول"
        verbose_name_plural = "تنوع‌های محصول"
        permissions = [
            ("can_manage_product_prices", "Can manage product prices"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "variant_fingerprint"],
                name="unique_product_variant_fingerprint",
            ),
            models.CheckConstraint(
                condition=Q(price__gte=1),
                name="variant_price_positive",
            ),
            models.CheckConstraint(
                condition=(
                    Q(
                        shipping_length_cm__isnull=True,
                        shipping_width_cm__isnull=True,
                        shipping_height_cm__isnull=True,
                    )
                    | Q(
                        shipping_length_cm__isnull=False,
                        shipping_width_cm__isnull=False,
                        shipping_height_cm__isnull=False,
                    )
                ),
                name="variant_shipping_dimensions_all_or_none",
            ),
            models.CheckConstraint(
                condition=Q(special_packaging_cost__gte=0),
                name="variant_special_packaging_cost_nonnegative",
            ),
        ]

    def __str__(self):
        parts = [self.product.name_fa]
        if self.flavor:
            parts.append(self.flavor)
        if self.weight:
            parts.append(self.weight)
        if self.size:
            parts.append(self.size)
        if self.servings is not None:
            parts.append(f"{self.servings} سروینگ")
        if self.color:
            parts.append(self.color)
        parts.extend(
            f"{key}: {value}"
            for key, value in sorted((self.attributes or {}).items())
        )
        return " - ".join(parts)

    def build_variant_fingerprint(self):
        identity = {
            "flavor": self.flavor or "",
            "weight": self.weight or "",
            "servings": self.servings,
            "size": self.size or "",
            "color": self.color or "",
            "attributes": self.attributes or {},
        }
        serialized = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def clean(self):
        super().clean()
        if not isinstance(self.attributes, dict) or any(
            not isinstance(key, str)
            or not key.strip()
            or not isinstance(value, (str, int, float, bool))
            for key, value in self.attributes.items()
        ):
            raise ValidationError(
                {"attributes": "ویژگی‌های سفارشی باید شیئی با کلید متنی و مقدار ساده باشند."}
            )
        self.variant_fingerprint = self.build_variant_fingerprint()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get("update_fields")
        identity_fields = {
            "flavor",
            "weight",
            "servings",
            "size",
            "color",
            "attributes",
        }
        if update_fields is None or identity_fields.intersection(update_fields):
            self.variant_fingerprint = self.build_variant_fingerprint()
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"variant_fingerprint"}

        # Auto-generate SKU if empty or a temporary admin-form placeholder.
        if not self.sku or self.sku.startswith("__TMP__"):
            from django.db import transaction

            with transaction.atomic():
                Product.objects.select_for_update().get(pk=self.product_id)
                self._generate_sku()
                if kwargs.get("update_fields") is not None:
                    kwargs["update_fields"] = set(kwargs["update_fields"]) | {"sku"}
                return super().save(*args, **kwargs)

        super().save(*args, **kwargs)

    def _generate_sku(self):
        brand_prefix = self.product.brand.name[:3].upper().replace(" ", "") or "PRD"
        prefix = f"{brand_prefix}-{self.product.id}-"

        existing_skus = ProductVariant.objects.filter(
            product=self.product
        ).values_list("sku", flat=True)

        max_num = 0
        for sku in existing_skus:
            if sku and sku.startswith(prefix):
                try:
                    number = int(sku[len(prefix) :])
                    max_num = max(max_num, number)
                except ValueError:
                    continue

        candidate = f"{prefix}{max_num + 1:03d}"

        # Safety: resolve any rare collision.
        while ProductVariant.objects.filter(sku=candidate).exists():
            candidate = (
                f"{prefix}{max_num + 1:03d}-{uuid.uuid4().hex[:4].upper()}"
            )

        self.sku = candidate



class ProductVariantPriceHistory(models.Model):
    CHANGE_TYPE_CHOICES = [
        ("manual", "تغییر دستی"),
        ("bulk", "تغییر گروهی"),
        ("import", "ورود فایل"),
        ("initial", "قیمت اولیه"),
    ]

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="price_history",
        verbose_name="تنوع محصول",
    )
    sku = models.CharField(max_length=100, db_index=True, verbose_name="SKU")
    product_name = models.CharField(max_length=200, verbose_name="نام محصول")
    old_price = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        null=True,
        blank=True,
        verbose_name="قیمت قبلی",
    )
    new_price = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        validators=[MinValueValidator(Decimal("1"))],
        verbose_name="قیمت جدید",
    )
    change_type = models.CharField(
        max_length=20,
        choices=CHANGE_TYPE_CHOICES,
        default="manual",
        verbose_name="نوع تغییر",
    )
    changed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="product_price_changes",
        verbose_name="تغییردهنده",
    )
    note = models.CharField(max_length=500, blank=True, verbose_name="توضیحات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="زمان تغییر")

    class Meta:
        verbose_name = "سابقه تغییر قیمت"
        verbose_name_plural = "سوابق تغییر قیمت"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["sku", "created_at"], name="variant_price_hist_sku_idx"),
        ]

    def __str__(self):
        return f"{self.sku}: {self.old_price or '—'} → {self.new_price}"



class DiscountCampaign(models.Model):
    SCOPE_CHOICES = [
        ("product", "محصول"),
        ("category", "دسته‌بندی"),
        ("brand", "برند"),
        ("cart", "سبد خرید"),
    ]
    DISCOUNT_TYPE_CHOICES = [
        ("percent", "درصدی"),
        ("fixed", "مبلغ ثابت"),
    ]

    name = models.CharField(max_length=160, verbose_name="نام کمپین")
    code = models.CharField(
        max_length=40,
        unique=True,
        null=True,
        blank=True,
        verbose_name="کد تخفیف",
        help_text="خالی باشد، تخفیف خودکار است؛ کدها بدون حساسیت به بزرگی حروف بررسی می‌شوند.",
    )
    scope = models.CharField(max_length=20, choices=SCOPE_CHOICES, verbose_name="دامنه")
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, null=True, blank=True,
        related_name="discount_campaigns", verbose_name="محصول",
    )
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, null=True, blank=True,
        related_name="discount_campaigns", verbose_name="دسته‌بندی",
    )
    brand = models.ForeignKey(
        Brand, on_delete=models.CASCADE, null=True, blank=True,
        related_name="discount_campaigns", verbose_name="برند",
    )
    discount_type = models.CharField(
        max_length=10, choices=DISCOUNT_TYPE_CHOICES, verbose_name="نوع تخفیف",
    )
    value = models.DecimalField(
        max_digits=12, decimal_places=0,
        validators=[MinValueValidator(Decimal("1"))],
        verbose_name="مقدار تخفیف",
        help_text="برای درصد عددی بین ۱ تا ۱۰۰ و برای مبلغ، تومان وارد شود.",
    )
    maximum_discount_amount = models.DecimalField(
        max_digits=12, decimal_places=0, null=True, blank=True,
        validators=[MinValueValidator(Decimal("1"))],
        verbose_name="سقف مبلغ تخفیف (تومان)",
    )
    minimum_order_amount = models.DecimalField(
        max_digits=12, decimal_places=0, default=0,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="حداقل مبلغ کالاها (تومان)",
    )
    starts_at = models.DateTimeField(verbose_name="شروع کمپین")
    ends_at = models.DateTimeField(verbose_name="پایان کمپین")
    priority = models.PositiveIntegerField(default=100, verbose_name="اولویت")
    is_stackable = models.BooleanField(default=False, verbose_name="قابل ترکیب با تخفیف دیگر")
    first_purchase_only = models.BooleanField(default=False, verbose_name="ویژه اولین خرید")
    max_uses = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)],
        verbose_name="حداکثر دفعات استفاده کل",
    )
    per_user_limit = models.PositiveIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1)],
        verbose_name="حداکثر استفاده هر مشتری",
    )
    usage_count = models.PositiveIntegerField(default=0, editable=False, verbose_name="تعداد استفاده")
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "کمپین تخفیف"
        verbose_name_plural = "کمپین‌های تخفیف"
        ordering = ["-priority", "-created_at"]
        indexes = [
            models.Index(fields=["is_active", "starts_at", "ends_at"], name="discount_active_window_idx"),
            models.Index(fields=["scope", "priority"], name="discount_scope_priority_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(value__gt=0), name="discount_value_positive"),
            models.CheckConstraint(condition=Q(minimum_order_amount__gte=0), name="discount_min_order_nonnegative"),
            models.CheckConstraint(
                condition=Q(discount_type="fixed") | Q(value__lte=100),
                name="discount_percent_max_100",
            ),
            models.CheckConstraint(
                condition=(
                    Q(scope="product", product__isnull=False, category__isnull=True, brand__isnull=True)
                    | Q(scope="category", product__isnull=True, category__isnull=False, brand__isnull=True)
                    | Q(scope="brand", product__isnull=True, category__isnull=True, brand__isnull=False)
                    | Q(scope="cart", product__isnull=True, category__isnull=True, brand__isnull=True)
                ),
                name="discount_scope_target_consistent",
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gt=models.F("starts_at")),
                name="discount_campaign_valid_window",
            ),
        ]

    def clean(self):
        super().clean()
        targets = {
            "product": self.product_id,
            "category": self.category_id,
            "brand": self.brand_id,
        }
        expected = self.scope if self.scope in targets else None
        if expected and not targets[expected]:
            raise ValidationError({expected: "برای این دامنه، هدف تخفیف الزامی است."})
        for scope, target_id in targets.items():
            if scope != expected and target_id:
                raise ValidationError({scope: "هدف انتخاب‌شده با دامنه تخفیف سازگار نیست."})
        if self.scope == "cart" and any(targets.values()):
            raise ValidationError("تخفیف سبد خرید نباید هدف محصول، دسته یا برند داشته باشد.")
        if self.discount_type == "percent" and self.value > 100:
            raise ValidationError({"value": "درصد تخفیف نمی‌تواند بیشتر از ۱۰۰ باشد."})
        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "پایان کمپین باید بعد از شروع آن باشد."})
        if self.code is not None:
            self.code = self.code.strip().upper() or None

    def save(self, *args, **kwargs):
        if self.code is not None:
            self.code = self.code.strip().upper() or None
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class DiscountRedemption(models.Model):
    campaign = models.ForeignKey(
        DiscountCampaign, on_delete=models.PROTECT,
        related_name="redemptions", verbose_name="کمپین",
    )
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT,
        related_name="discount_redemptions", verbose_name="سفارش",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="discount_redemptions", verbose_name="مشتری",
    )
    discount_amount = models.DecimalField(
        max_digits=12, decimal_places=0,
        validators=[MinValueValidator(Decimal("0"))],
        verbose_name="مبلغ تخفیف استفاده‌شده",
    )
    code_used = models.CharField(max_length=40, blank=True, verbose_name="کد استفاده‌شده")
    status = models.CharField(
        max_length=12,
        choices=[
            ("reserved", "رزروشده"),
            ("consumed", "مصرف‌شده"),
            ("released", "آزادشده"),
        ],
        default="reserved",
        verbose_name="وضعیت مصرف",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "استفاده از تخفیف"
        verbose_name_plural = "استفاده‌های تخفیف"
        constraints = [
            models.UniqueConstraint(fields=["campaign", "order"], name="unique_discount_per_order"),
            models.CheckConstraint(
                condition=Q(discount_amount__gte=0),
                name="discount_redemption_amount_nonnegative",
            ),
        ]
        indexes = [
            models.Index(fields=["campaign", "user"], name="discount_redemption_user_idx"),
        ]

    def __str__(self):
        return f"{self.campaign} - {self.order}"
