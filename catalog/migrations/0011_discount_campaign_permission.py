from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0010_product_catalog_management_permission"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="discountcampaign",
            options={
                "verbose_name": "کمپین تخفیف",
                "verbose_name_plural": "کمپین‌های تخفیف",
                "ordering": ["-priority", "-created_at"],
                "permissions": [
                    ("can_manage_discount_campaigns", "Can manage discount campaigns"),
                ],
            },
        ),
    ]
