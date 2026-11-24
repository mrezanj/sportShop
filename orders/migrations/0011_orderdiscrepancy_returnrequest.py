import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import jalali_suite.models


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("orders", "0010_orderitem_discount_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "در انتظار پرداخت"), ("paid", "پرداخت شده"),
                    ("processing", "در حال پردازش"), ("shipped", "ارسال شده"),
                    ("delivered", "تحویل شده"), ("cancelled", "لغو شده"),
                    ("discrepancy", "دارای مغایرت"),
                ],
                default="pending", max_length=20, verbose_name="وضعیت",
            ),
        ),
        migrations.CreateModel(
            name="OrderDiscrepancy",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("open", "در حال بررسی"), ("resolved", "رسیدگی‌شده")], default="open", max_length=20, verbose_name="وضعیت پرونده")),
                ("reason", models.TextField(verbose_name="شرح مغایرت")),
                ("resolution", models.TextField(blank=True, verbose_name="نتیجه رسیدگی")),
                ("previous_order_status", models.CharField(blank=True, choices=[("pending", "در انتظار پرداخت"), ("paid", "پرداخت شده"), ("processing", "در حال پردازش"), ("shipped", "ارسال شده"), ("delivered", "تحویل شده"), ("cancelled", "لغو شده"), ("discrepancy", "دارای مغایرت")], max_length=20, verbose_name="وضعیت سفارش پیش از توقف")),
                ("created_at", jalali_suite.models.JalaliDateTimeField(auto_now_add=True, verbose_name="زمان ثبت")),
                ("resolved_at", models.DateTimeField(blank=True, null=True, verbose_name="زمان رسیدگی")),
                ("opened_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="opened_order_discrepancies", to=settings.AUTH_USER_MODEL, verbose_name="ثبت‌کننده")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="discrepancies", to="orders.order", verbose_name="سفارش")),
                ("resolved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="resolved_order_discrepancies", to=settings.AUTH_USER_MODEL, verbose_name="رسیدگی‌کننده")),
            ],
            options={
                "verbose_name": "مغایرت سفارش", "verbose_name_plural": "مغایرت‌های سفارش",
                "ordering": ["-created_at", "-id"],
                "permissions": [("can_manage_order_discrepancies", "Can manage order discrepancies")],
            },
        ),
        migrations.CreateModel(
            name="ReturnRequest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("reason", models.TextField(verbose_name="علت درخواست")),
                ("status", models.CharField(choices=[("requested", "درخواست‌شده"), ("approved", "تأییدشده"), ("rejected", "ردشده"), ("received", "دریافت و بررسی‌شده"), ("closed", "بسته‌شده")], default="requested", max_length=20, verbose_name="وضعیت")),
                ("staff_note", models.TextField(blank=True, verbose_name="یادداشت بررسی")),
                ("created_at", jalali_suite.models.JalaliDateTimeField(auto_now_add=True, verbose_name="زمان درخواست")),
                ("updated_at", jalali_suite.models.JalaliDateTimeField(auto_now=True, verbose_name="آخرین بروزرسانی")),
                ("order", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="return_requests", to="orders.order", verbose_name="سفارش")),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_return_requests", to=settings.AUTH_USER_MODEL, verbose_name="بررسی‌کننده")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="return_requests", to=settings.AUTH_USER_MODEL, verbose_name="مشتری")),
            ],
            options={
                "verbose_name": "درخواست مرجوعی", "verbose_name_plural": "درخواست‌های مرجوعی",
                "ordering": ["-created_at", "-id"],
                "permissions": [("can_review_return_requests", "Can review return requests")],
            },
        ),
        migrations.CreateModel(
            name="ReturnRequestItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("quantity", models.PositiveIntegerField(verbose_name="تعداد درخواستی")),
                ("order_item", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="return_request_items", to="orders.orderitem", verbose_name="قلم سفارش")),
                ("return_request", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="orders.returnrequest", verbose_name="درخواست مرجوعی")),
            ],
            options={"verbose_name": "قلم مرجوعی", "verbose_name_plural": "اقلام مرجوعی"},
        ),
        migrations.AddConstraint(model_name="orderdiscrepancy", constraint=models.UniqueConstraint(condition=models.Q(("status", "open")), fields=("order",), name="unique_open_order_discrepancy")),
        migrations.AddConstraint(model_name="returnrequest", constraint=models.UniqueConstraint(condition=models.Q(("status__in", ["requested", "approved", "received"])), fields=("order",), name="unique_active_return_request_per_order")),
        migrations.AddConstraint(model_name="returnrequestitem", constraint=models.UniqueConstraint(fields=("return_request", "order_item"), name="unique_return_request_order_item")),
        migrations.AddConstraint(model_name="returnrequestitem", constraint=models.CheckConstraint(condition=models.Q(("quantity__gt", 0)), name="return_request_item_quantity_positive")),
    ]
