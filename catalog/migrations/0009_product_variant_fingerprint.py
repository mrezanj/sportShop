import hashlib
import json

from django.db import migrations, models


def populate_variant_fingerprints(apps, schema_editor):
    ProductVariant = apps.get_model("catalog", "ProductVariant")
    alias = schema_editor.connection.alias
    for variant in ProductVariant.objects.using(alias).all().iterator():
        identity = {
            "flavor": variant.flavor or "",
            "weight": variant.weight or "",
            "servings": variant.servings,
            "size": variant.size or "",
            "color": variant.color or "",
            "attributes": variant.attributes or {},
        }
        serialized = json.dumps(
            identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        ProductVariant.objects.using(alias).filter(pk=variant.pk).update(
            variant_fingerprint=fingerprint
        )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0008_discount_campaign"),
    ]

    operations = [
        migrations.AddField(
            model_name="productvariant",
            name="variant_fingerprint",
            field=models.CharField(
                blank=True,
                default="",
                editable=False,
                max_length=64,
                verbose_name="شناسه ترکیب ویژگی‌های تنوع",
            ),
        ),
        migrations.RunPython(
            populate_variant_fingerprints,
            migrations.RunPython.noop,
        ),
        migrations.AlterUniqueTogether(
            name="productvariant",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="productvariant",
            constraint=models.UniqueConstraint(
                fields=("product", "variant_fingerprint"),
                name="unique_product_variant_fingerprint",
            ),
        ),
    ]
