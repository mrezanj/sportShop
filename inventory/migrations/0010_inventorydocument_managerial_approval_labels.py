from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0009_optional_inventory_batch_number"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="inventorydocument",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "پیش‌نویس"),
                    ("pending_review", "در انتظار بررسی حسابدار"),
                    ("pending_approval", "در انتظار تأیید مدیریتی"),
                    ("approved", "تأیید نهایی"),
                    ("rejected", "رد شده"),
                    ("cancelled", "لغو شده"),
                ],
                default="draft",
                max_length=20,
                verbose_name="وضعیت",
            ),
        ),
        migrations.AlterField(
            model_name="inventorydocument",
            name="approved_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="approved_inventory_documents",
                to=settings.AUTH_USER_MODEL,
                verbose_name="تأییدکننده مدیریتی",
            ),
        ),
    ]
