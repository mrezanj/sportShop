import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0008_order_pricing_snapshot"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CheckoutPriceQuote",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("payload", models.JSONField(verbose_name="جزئیات قیمت تأییدشده")),
                ("expires_at", models.DateTimeField(verbose_name="زمان انقضای پیش‌نمایش")),
                ("consumed_at", models.DateTimeField(blank=True, null=True, verbose_name="زمان استفاده")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="checkout_price_quotes", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "پیش‌نمایش قیمت تسویه",
                "verbose_name_plural": "پیش‌نمایش‌های قیمت تسویه",
            },
        ),
        migrations.AddIndex(
            model_name="checkoutpricequote",
            index=models.Index(fields=["user", "expires_at"], name="checkout_quote_user_exp_idx"),
        ),
    ]
