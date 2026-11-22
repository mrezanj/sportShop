
import uuid

from django.db import migrations, models


def populate_request_keys(apps, schema_editor):
    Payment = apps.get_model("payments", "Payment")
    database = schema_editor.connection.alias

    payments = (
        Payment.objects.using(database)
        .filter(request_key__isnull=True)
        .only("pk")
    )

    for payment in payments.iterator():
        payment.request_key = uuid.uuid4()
        payment.save(
            using=database,
            update_fields=["request_key"],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("payments", "0002_alter_payment_created_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="request_key",
            field=models.UUIDField(
                null=True,
                blank=True,
                editable=False,
                verbose_name="شناسه یکتای درخواست پرداخت",
            ),
        ),
        migrations.RunPython(
            populate_request_keys,
            migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="payment",
            name="request_key",
            field=models.UUIDField(
                default=uuid.uuid4,
                unique=True,
                editable=False,
                verbose_name="شناسه یکتای درخواست پرداخت",
            ),
        ),
    ]
