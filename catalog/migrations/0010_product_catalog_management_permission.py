from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0009_product_variant_fingerprint"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="product",
            options={
                "verbose_name": "محصول",
                "verbose_name_plural": "محصولات",
                "ordering": ["-created_at"],
                "permissions": [
                    ("can_manage_catalog", "Can manage catalog products, categories and brands"),
                ],
            },
        ),
    ]
