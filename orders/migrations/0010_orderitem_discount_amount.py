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
        migrations.AlterField(
            model_name="orderitem",
            name="subtotal",
            field=models.DecimalField(
                decimal_places=0,
                max_digits=12,
                verbose_name="جمع قبل از تخفیف",
            ),
        ),
        migrations.AddConstraint(
            model_name="orderitem",
            constraint=models.CheckConstraint(
                condition=(models.Q(("discount_amount__gte", 0)) & models.Q(("discount_amount__lte", models.F("subtotal")))),
                name="order_item_discount_within_subtotal",
            ),
        ),
    ]
