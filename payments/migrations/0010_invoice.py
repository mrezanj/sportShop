import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0012_returnrequesthistory"),
        ("payments", "0009_refundhistory"),
    ]

    operations = [
        migrations.CreateModel(
            name="Invoice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("invoice_number", models.CharField(editable=False, max_length=32, unique=True, verbose_name="شماره فاکتور")),
                ("snapshot", models.JSONField(default=dict, verbose_name="اطلاعات ثابت فاکتور")),
                ("issued_at", models.DateTimeField(auto_now_add=True, verbose_name="زمان صدور")),
                ("order", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="invoice", to="orders.order", verbose_name="سفارش")),
                ("payment", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="invoices", to="payments.payment", verbose_name="پرداخت تأییدشده")),
            ],
            options={
                "verbose_name": "فاکتور فروش",
                "verbose_name_plural": "فاکتورهای فروش",
                "ordering": ["-issued_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="invoice",
            constraint=models.UniqueConstraint(fields=("payment",), name="unique_invoice_payment"),
        ),
    ]
