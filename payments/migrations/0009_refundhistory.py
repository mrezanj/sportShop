import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import jalali_suite.models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0012_returnrequesthistory"),
        ("payments", "0008_refund"),
    ]

    operations = [
        migrations.CreateModel(
            name="RefundHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("old_status", models.CharField(blank=True, default="", max_length=20)),
                ("new_status", models.CharField(choices=[("requested", "درخواست‌شده"), ("approved", "تأییدشده"), ("processing", "در حال انجام"), ("succeeded", "انجام‌شده"), ("failed", "ناموفق"), ("rejected", "ردشده")], max_length=20)),
                ("provider_reference", models.CharField(blank=True, max_length=200)),
                ("provider_response", models.JSONField(blank=True, default=dict)),
                ("note", models.TextField(blank=True)),
                ("created_at", jalali_suite.models.JalaliDateTimeField(auto_now_add=True)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="refund_status_changes", to=settings.AUTH_USER_MODEL)),
                ("refund", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="history", to="payments.refund", verbose_name="بازپرداخت")),
            ],
            options={
                "verbose_name": "تاریخچه بازپرداخت",
                "verbose_name_plural": "تاریخچه بازپرداخت‌ها",
                "ordering": ["created_at", "id"],
            },
        ),
    ]
