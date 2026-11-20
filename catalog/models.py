import uuid
from django.db import models
from django.db.models import Q, UniqueConstraint
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
    requires_cold_shipping = models.BooleanField(
        default=False, verbose_name="نیاز به ارسال سرد"
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "محصول"
        verbose_name_plural = "محصولات"
        ordering = ["-created_at"]

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

    def save(self, *args, **kwargs):
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
        product = self.product
        was_primary = self.is_primary
        super().delete(*args, **kwargs)
        # If the deleted image was primary, promote another one
        if was_primary:
            first_remaining = ProductImage.objects.filter(product=product).first()
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
    weight = models.CharField(max_length=50, blank=True, verbose_name="وزن (مثلاً 2kg)")
    servings = models.PositiveIntegerField(
        null=True, blank=True, verbose_name="تعداد سروینگ"
    )
    size = models.CharField(max_length=20, blank=True, verbose_name="سایز (برای پوشاک)")
    color = models.CharField(max_length=50, blank=True, verbose_name="رنگ")
    sku = models.CharField(
        max_length=100, unique=True, blank=True, verbose_name="کد انبار (SKU)"
    )
    price = models.DecimalField(
        max_digits=12, decimal_places=0, verbose_name="قیمت (تومان)"
    )
    stock = models.PositiveIntegerField(default=0, verbose_name="موجودی")
    is_active = models.BooleanField(default=True, verbose_name="فعال")

    class Meta:
        verbose_name = "تنوع محصول"
        verbose_name_plural = "تنوع‌های محصول"
        unique_together = ["product", "flavor", "weight", "size", "color"]

    def __str__(self):
        parts = [self.product.name_fa]
        if self.flavor:
            parts.append(self.flavor)
        if self.weight:
            parts.append(self.weight)
        if self.size:
            parts.append(self.size)
        if self.color:
            parts.append(self.color)
        return " - ".join(parts)

    def save(self, *args, **kwargs):
        # Auto-generate SKU if:
        # - empty (new variant with no manual SKU), OR
        # - starts with __TMP__ (placeholder from ProductVariantForm.clean_sku)
        if not self.sku or self.sku.startswith("__TMP__"):
            brand_prefix = self.product.brand.name[:3].upper().replace(" ", "") or "PRD"
            prefix = f"{brand_prefix}-{self.product.id}-"

            existing_skus = ProductVariant.objects.filter(
                product=self.product
            ).values_list("sku", flat=True)

            max_num = 0
            for s in existing_skus:
                if s and s.startswith(prefix):
                    try:
                        n = int(s[len(prefix) :])
                        max_num = max(max_num, n)
                    except ValueError:
                        continue

            candidate = f"{prefix}{max_num + 1:03d}"

            # Safety: resolve any rare collision
            while ProductVariant.objects.filter(sku=candidate).exists():
                candidate = (
                    f"{prefix}{max_num + 1:03d}-" f"{uuid.uuid4().hex[:4].upper()}"
                )

            self.sku = candidate

        super().save(*args, **kwargs)
