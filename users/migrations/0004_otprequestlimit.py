from django.db import migrations, models


def migrate_existing_otp_limits(apps, schema_editor):
    OTPCode = apps.get_model("users", "OTPCode")
    OTPRequestLimit = apps.get_model("users", "OTPRequestLimit")

    database = schema_editor.connection.alias
    connection = schema_editor.connection

    quote = connection.ops.quote_name

    table = quote(OTPCode._meta.db_table)
    mobile_col = quote("mobile")
    purpose_col = quote("purpose")
    created_col = quote("created_at")

    sql = (
        f"SELECT {mobile_col}, MAX({created_col}) "
        f"FROM {table} "
        f"WHERE {purpose_col} = %s "
        f"GROUP BY {mobile_col}"
    )

    with connection.cursor() as cursor:
        cursor.execute(sql, ["login"])
        rows = cursor.fetchall()

    OTPRequestLimit.objects.using(database).bulk_create(
        [
            OTPRequestLimit(
                mobile=mobile,
                purpose="login",
                last_requested_at=last_requested_at,
            )
            for mobile, last_requested_at in rows
        ],
        batch_size=500,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_otpcode_attempt_count"),
    ]

    operations = [
        migrations.CreateModel(
            name="OTPRequestLimit",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("mobile", models.CharField(max_length=11)),
                ("purpose", models.CharField(max_length=20)),
                (
                    "last_requested_at",
                    models.DateTimeField(blank=True, null=True),
                ),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(
                        fields=("mobile", "purpose"),
                        name="unique_otp_request_limit",
                    ),
                ],
            },
        ),
        migrations.RunPython(
            migrate_existing_otp_limits,
            migrations.RunPython.noop,
        ),
    ]
