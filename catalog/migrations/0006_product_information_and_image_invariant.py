# Generated for product information and catalog invariants.
from django.db import migrations, models


def keep_one_primary_image(apps, schema_editor):
    ProductImage = apps.get_model("catalog", "ProductImage")
    database = schema_editor.connection.alias

    product_ids = (
        ProductImage.objects.using(database)
        .filter(is_primary=True)
        .values_list("product_id", flat=True)
        .distinct()
    )
    for product_id in product_ids.iterator():
        primary_ids = list(
            ProductImage.objects.using(database)
            .filter(product_id=product_id, is_primary=True)
            .order_by("order", "id")
            .values_list("id", flat=True)
        )
        if len(primary_ids) > 1:
            ProductImage.objects.using(database).filter(
                id__in=primary_ids[1:]
            ).update(is_primary=False)


class Migration(migrations.Migration):
    dependencies = [("catalog", "0005_productvariant_requires_special_packaging_and_more")]

    operations = [
        migrations.AddField(
            model_name="product",
            name="contraindications",
            field=models.TextField(blank=True, verbose_name="موارد منع مصرف"),
        ),
        migrations.AddField(
            model_name="product",
            name="medical_advice",
            field=models.TextField(blank=True, verbose_name="توصیه پزشکی"),
        ),
        migrations.AddField(
            model_name="product",
            name="license_id",
            field=models.CharField(blank=True, max_length=150, verbose_name="شناسه مجوز"),
        ),
        migrations.AddField(
            model_name="product",
            name="authenticity_code",
            field=models.CharField(blank=True, max_length=150, verbose_name="شناسه اصالت"),
        ),
        migrations.AddField(
            model_name="product",
            name="license_details",
            field=models.TextField(blank=True, verbose_name="اطلاعات تکمیلی مجوز و اصالت"),
        ),
        migrations.AddField(
            model_name="product",
            name="consumption_goals",
            field=models.JSONField(blank=True, default=list, verbose_name="اهداف مصرف", help_text="فهرستی از اهداف مصرف؛ مانند افزایش حجم، کاهش وزن یا سلامت عمومی."),
        ),
        migrations.AddField(
            model_name="productvariant",
            name="attributes",
            field=models.JSONField(blank=True, default=dict, verbose_name="ویژگی‌های سفارشی", help_text="ویژگی‌های اختصاصی این تنوع به‌صورت شیء JSON؛ مثال: {\"serving_type\": \"کپسول\", \"material\": \"پلی‌استر\"}."),
        ),
        migrations.RunPython(keep_one_primary_image, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="productimage",
            constraint=models.UniqueConstraint(condition=models.Q(("is_primary", True)), fields=("product",), name="unique_primary_image_per_product"),
        ),
    ]
