from django.db import migrations, models
from django.core.validators import MinValueValidator


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0007_convert_shipping_cities_to_foreign_keys"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="discount_amount",
            field=models.DecimalField(decimal_places=0, default=0, max_digits=12, validators=[MinValueValidator(0)], verbose_name="مبلغ تخفیف"),
        ),
        migrations.AddField(
            model_name="order",
            name="pricing_snapshot",
            field=models.JSONField(blank=True, default=dict, verbose_name="تصویر ثابت قیمت‌گذاری سفارش"),
        ),
    ]
