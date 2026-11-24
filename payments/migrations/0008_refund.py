import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import jalali_suite.models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0011_orderdiscrepancy_returnrequest"),
        ("payments", "0007_mockgatewaytransaction"),
    ]

    operations = [
        migrations.CreateModel(
            name="Refund",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("amount", models.DecimalField(decimal_places=0, max_digits=12, verbose_name="مبلغ بازپرداخت (تومان)")),
                ("status", models.CharField(choices=[("requested", "درخواست‌شده"), ("approved", "تأییدشده"), ("processing", "در حال انجام"), ("succeeded", "انجام‌شده"), ("failed", "ناموفق"), ("rejected", "ردشده")], default="requested", max_length=20, verbose_name="وضعیت")),
                ("idempotency_key", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("provider_reference", models.CharField(blank=True, max_length=200, verbose_name="شناسه پیگیری ارائه‌دهنده")),
                ("provider_response", models.JSONField(blank=True, default=dict, verbose_name="پاسخ ارائه‌دهنده")),
                ("created_at", jalali_suite.models.JalaliDateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("payment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="refunds", to="payments.payment", verbose_name="پرداخت مبنا")),
                ("processed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="processed_refunds", to=settings.AUTH_USER_MODEL)),
                ("requested_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="requested_refunds", to=settings.AUTH_USER_MODEL)),
                ("return_request", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="refunds", to="orders.returnrequest", verbose_name="درخواست مرجوعی")),
            ],
            options={
                "verbose_name": "بازپرداخت", "verbose_name_plural": "بازپرداخت‌ها",
                "ordering": ["-created_at", "-id"],
                "permissions": [("can_manage_refunds", "Can manage refunds")],
            },
        ),
        migrations.AddConstraint(model_name="refund", constraint=models.CheckConstraint(condition=models.Q(("amount__gt", 0)), name="refund_amount_positive")),
    ]
