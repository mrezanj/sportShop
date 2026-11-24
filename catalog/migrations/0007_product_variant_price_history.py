from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0006_product_information_and_image_invariant"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="productvariant",
            options={
                "verbose_name": "تنوع محصول",
                "verbose_name_plural": "تنوع‌های محصول",
                "unique_together": {("product", "flavor", "weight", "size", "color")},
                "permissions": [
                    ("can_manage_product_prices", "Can manage product prices"),
                ],
            },
        ),
        migrations.AlterField(
            model_name="productvariant",
            name="price",
            field=models.DecimalField(
                decimal_places=0,
                max_digits=12,
                validators=[MinValueValidator(Decimal("1"))],
                verbose_name="قیمت (تومان)",
            ),
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.CheckConstraint(
                condition=models.Q(price__gte=1),
                name="variant_price_positive",
            ),
        ),
        migrations.CreateModel(
            name="ProductVariantPriceHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sku", models.CharField(db_index=True, max_length=100, verbose_name="SKU")),
                ("product_name", models.CharField(max_length=200, verbose_name="نام محصول")),
                ("old_price", models.DecimalField(blank=True, decimal_places=0, max_digits=12, null=True, verbose_name="قیمت قبلی")),
                ("new_price", models.DecimalField(decimal_places=0, max_digits=12, validators=[MinValueValidator(Decimal("1"))], verbose_name="قیمت جدید")),
                ("change_type", models.CharField(choices=[("manual", "تغییر دستی"), ("bulk", "تغییر گروهی"), ("import", "ورود فایل"), ("initial", "قیمت اولیه")], default="manual", max_length=20, verbose_name="نوع تغییر")),
                ("note", models.CharField(blank=True, max_length=500, verbose_name="توضیحات")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="زمان تغییر")),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="product_price_changes", to=settings.AUTH_USER_MODEL, verbose_name="تغییردهنده")),
                ("variant", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="price_history", to="catalog.productvariant", verbose_name="تنوع محصول")),
            ],
            options={
                "verbose_name": "سابقه تغییر قیمت",
                "verbose_name_plural": "سوابق تغییر قیمت",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="productvariantpricehistory",
            index=models.Index(fields=["sku", "created_at"], name="variant_price_hist_sku_idx"),
        ),
    ]
