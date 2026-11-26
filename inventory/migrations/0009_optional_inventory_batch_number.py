from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0008_inventorydocument_created_by_type_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="inventorybatch",
            name="unique_variant_batch_number",
        ),
        migrations.AlterField(
            model_name="inventorybatch",
            name="batch_number",
            field=models.CharField(
                blank=True,
                default="",
                help_text="در صورت نداشتن شماره بچ واقعی، این فیلد خالی می‌ماند.",
                max_length=100,
                verbose_name="شماره بچ",
            ),
        ),
        migrations.AddConstraint(
            model_name="inventorybatch",
            constraint=models.UniqueConstraint(
                condition=~models.Q(batch_number=""),
                fields=("variant", "batch_number"),
                name="unique_variant_batch_number",
            ),
        ),
    ]
