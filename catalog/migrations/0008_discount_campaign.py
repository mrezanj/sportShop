# Generated manually for the discount engine.
import django.core.validators
from decimal import Decimal
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0007_product_variant_price_history"),
        ("orders", "0009_checkout_price_quote"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="DiscountCampaign",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=160, verbose_name="نام کمپین")),
                ("code", models.CharField(blank=True, max_length=40, null=True, unique=True, verbose_name="کد تخفیف", help_text="خالی باشد، تخفیف خودکار است؛ کدها بدون حساسیت به بزرگی حروف بررسی می‌شوند.")),
                ("scope", models.CharField(choices=[("product", "محصول"), ("category", "دسته‌بندی"), ("brand", "برند"), ("cart", "سبد خرید")], max_length=20, verbose_name="دامنه")),
                ("discount_type", models.CharField(choices=[("percent", "درصدی"), ("fixed", "مبلغ ثابت")], max_length=10, verbose_name="نوع تخفیف")),
                ("value", models.DecimalField(decimal_places=0, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("1"))], verbose_name="مقدار تخفیف", help_text="برای درصد عددی بین ۱ تا ۱۰۰ و برای مبلغ، تومان وارد شود.")),
                ("maximum_discount_amount", models.DecimalField(blank=True, decimal_places=0, max_digits=12, null=True, validators=[django.core.validators.MinValueValidator(Decimal("1"))], verbose_name="سقف مبلغ تخفیف (تومان)")),
                ("minimum_order_amount", models.DecimalField(decimal_places=0, default=0, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0"))], verbose_name="حداقل مبلغ کالاها (تومان)")),
                ("starts_at", models.DateTimeField(verbose_name="شروع کمپین")),
                ("ends_at", models.DateTimeField(verbose_name="پایان کمپین")),
                ("priority", models.PositiveIntegerField(default=100, verbose_name="اولویت")),
                ("is_stackable", models.BooleanField(default=False, verbose_name="قابل ترکیب با تخفیف دیگر")),
                ("first_purchase_only", models.BooleanField(default=False, verbose_name="ویژه اولین خرید")),
                ("max_uses", models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)], verbose_name="حداکثر دفعات استفاده کل")),
                ("per_user_limit", models.PositiveIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(1)], verbose_name="حداکثر استفاده هر مشتری")),
                ("usage_count", models.PositiveIntegerField(default=0, editable=False, verbose_name="تعداد استفاده")),
                ("is_active", models.BooleanField(default=True, verbose_name="فعال")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("brand", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="discount_campaigns", to="catalog.brand", verbose_name="برند")),
                ("category", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="discount_campaigns", to="catalog.category", verbose_name="دسته‌بندی")),
                ("product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="discount_campaigns", to="catalog.product", verbose_name="محصول")),
            ],
            options={
                "verbose_name": "کمپین تخفیف",
                "verbose_name_plural": "کمپین‌های تخفیف",
                "ordering": ["-priority", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="DiscountRedemption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("discount_amount", models.DecimalField(decimal_places=0, max_digits=12, validators=[django.core.validators.MinValueValidator(Decimal("0"))], verbose_name="مبلغ تخفیف استفاده‌شده")),
                ("code_used", models.CharField(blank=True, max_length=40, verbose_name="کد استفاده‌شده")),
                ("status", models.CharField(choices=[("reserved", "رزروشده"), ("consumed", "مصرف‌شده"), ("released", "آزادشده")], default="reserved", max_length=12, verbose_name="وضعیت مصرف")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("campaign", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="redemptions", to="catalog.discountcampaign", verbose_name="کمپین")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="discount_redemptions", to="orders.order", verbose_name="سفارش")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="discount_redemptions", to=settings.AUTH_USER_MODEL, verbose_name="مشتری")),
            ],
            options={
                "verbose_name": "استفاده از تخفیف",
                "verbose_name_plural": "استفاده‌های تخفیف",
            },
        ),
        migrations.AddIndex(
            model_name="discountcampaign",
            index=models.Index(fields=["is_active", "starts_at", "ends_at"], name="discount_active_window_idx"),
        ),
        migrations.AddIndex(
            model_name="discountcampaign",
            index=models.Index(fields=["scope", "priority"], name="discount_scope_priority_idx"),
        ),
        migrations.AddConstraint(
            model_name="discountcampaign",
            constraint=models.CheckConstraint(condition=models.Q(("value__gt", 0)), name="discount_value_positive"),
        ),
        migrations.AddConstraint(
            model_name="discountcampaign",
            constraint=models.CheckConstraint(condition=models.Q(("minimum_order_amount__gte", 0)), name="discount_min_order_nonnegative"),
        ),
        migrations.AddConstraint(
            model_name="discountcampaign",
            constraint=models.CheckConstraint(
                condition=models.Q(("discount_type", "fixed")) | models.Q(("value__lte", 100)),
                name="discount_percent_max_100",
            ),
        ),
        migrations.AddConstraint(
            model_name="discountcampaign",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(("brand__isnull", True), ("category__isnull", True), ("product__isnull", False), ("scope", "product"))
                    | models.Q(("brand__isnull", True), ("category__isnull", False), ("product__isnull", True), ("scope", "category"))
                    | models.Q(("brand__isnull", False), ("category__isnull", True), ("product__isnull", True), ("scope", "brand"))
                    | models.Q(("brand__isnull", True), ("category__isnull", True), ("product__isnull", True), ("scope", "cart"))
                ),
                name="discount_scope_target_consistent",
            ),
        ),
        migrations.AddConstraint(
            model_name="discountcampaign",
            constraint=models.CheckConstraint(condition=models.Q(("ends_at__gt", models.F("starts_at"))), name="discount_campaign_valid_window"),
        ),
        migrations.AddConstraint(
            model_name="discountredemption",
            constraint=models.UniqueConstraint(fields=("campaign", "order"), name="unique_discount_per_order"),
        ),
        migrations.AddConstraint(
            model_name="discountredemption",
            constraint=models.CheckConstraint(
                condition=models.Q(("discount_amount__gte", 0)),
                name="discount_redemption_amount_nonnegative",
            ),
        ),
        migrations.AddIndex(
            model_name="discountredemption",
            index=models.Index(fields=["campaign", "user"], name="discount_redemption_user_idx"),
        ),
    ]
