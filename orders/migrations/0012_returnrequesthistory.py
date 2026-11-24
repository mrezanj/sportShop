import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import jalali_suite.models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0011_orderdiscrepancy_returnrequest"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReturnRequestHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("old_status", models.CharField(blank=True, default="", max_length=20)),
                ("new_status", models.CharField(choices=[("requested", "درخواست‌شده"), ("approved", "تأییدشده"), ("rejected", "ردشده"), ("received", "دریافت و بررسی‌شده"), ("closed", "بسته‌شده")], max_length=20)),
                ("note", models.TextField(blank=True)),
                ("created_at", jalali_suite.models.JalaliDateTimeField(auto_now_add=True)),
                ("changed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="return_request_status_changes", to=settings.AUTH_USER_MODEL)),
                ("return_request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="history", to="orders.returnrequest", verbose_name="درخواست مرجوعی")),
            ],
            options={
                "verbose_name": "تاریخچه مرجوعی",
                "verbose_name_plural": "تاریخچه مرجوعی‌ها",
                "ordering": ["created_at", "id"],
            },
        ),
    ]
