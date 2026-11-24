from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0009_checkout_price_quote"),
    ]

    operations = [
        migrations.AddField(
            model_name="orderitem",
            name="discount_amount",
            field=models.DecimalField(
                decimal_places=0,
                default=0,
                max_digits=12,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="تخفیف قلم سفارش",
            ),
        ),
    ]
