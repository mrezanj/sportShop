
from django.db import migrations, models
import django.db.models.deletion


def forwards(apps, schema_editor):
    db_alias = schema_editor.connection.alias

    City = apps.get_model("locations", "City")
    ShippingRate = apps.get_model("orders", "ShippingRate")
    ShippingMethod = apps.get_model("orders", "ShippingMethod")

    cities = list(
        City.objects.using(db_alias).select_related("province").all()
    )

    city_assignments = []
    method_assignments = []
    errors = []

    for rate in ShippingRate.objects.using(db_alias).all():
        legacy_name = (rate.legacy_city or "").strip()

        if not legacy_name:
            continue

        matches = [
            city
            for city in cities
            if city.province.slug == rate.province
            and city.name.strip().casefold() == legacy_name.casefold()
        ]

        if len(matches) != 1:
            errors.append(
                f"ShippingRate id={rate.pk}: "
                f"province={rate.province!r}, city={legacy_name!r}, "
                f"matches={len(matches)}"
            )
            continue

        city_assignments.append((rate.pk, matches[0].pk))

    for method in ShippingMethod.objects.using(db_alias).all():
        legacy_name = (
            method.legacy_restricted_city or ""
        ).strip()

        if not legacy_name:
            continue

        province = (method.restricted_province or "").strip()

        if not province:
            errors.append(
                f"ShippingMethod id={method.pk}: "
                f"restricted city={legacy_name!r} has no province"
            )
            continue

        matches = [
            city
            for city in cities
            if city.province.slug == province
            and city.name.strip().casefold() == legacy_name.casefold()
        ]

        if len(matches) != 1:
            errors.append(
                f"ShippingMethod id={method.pk}: "
                f"province={province!r}, city={legacy_name!r}, "
                f"matches={len(matches)}"
            )
            continue

        method_assignments.append((method.pk, matches[0].pk))

    if errors:
        details = "\n".join(errors)
        raise RuntimeError(
            "Shipping city migration stopped because some legacy "
            "city names could not be matched unambiguously:\n"
            + details
        )

    for rate_id, city_id in city_assignments:
        ShippingRate.objects.using(db_alias).filter(
            pk=rate_id
        ).update(city_id=city_id)

    for method_id, city_id in method_assignments:
        ShippingMethod.objects.using(db_alias).filter(
            pk=method_id
        ).update(restricted_city_id=city_id)


def backwards(apps, schema_editor):
    db_alias = schema_editor.connection.alias

    ShippingRate = apps.get_model("orders", "ShippingRate")
    ShippingMethod = apps.get_model("orders", "ShippingMethod")

    rates = (
        ShippingRate.objects.using(db_alias)
        .select_related("city")
        .all()
    )

    for rate in rates:
        legacy_name = rate.city.name if rate.city_id else ""
        ShippingRate.objects.using(db_alias).filter(
            pk=rate.pk
        ).update(legacy_city=legacy_name)

    methods = (
        ShippingMethod.objects.using(db_alias)
        .select_related("restricted_city")
        .all()
    )

    for method in methods:
        legacy_name = (
            method.restricted_city.name
            if method.restricted_city_id
            else ""
        )
        ShippingMethod.objects.using(db_alias).filter(
            pk=method.pk
        ).update(legacy_restricted_city=legacy_name)


class Migration(migrations.Migration):

    dependencies = [
        (
            "locations",
            "0001_initial",
        ),
        (
            "orders",
            "0006_shippingconfiguration_alter_order_options_and_more",
        ),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="shippingrate",
            name="unique_shipping_method_province_city",
        ),

        migrations.RenameField(
            model_name="shippingrate",
            old_name="city",
            new_name="legacy_city",
        ),

        migrations.RenameField(
            model_name="shippingmethod",
            old_name="restricted_city",
            new_name="legacy_restricted_city",
        ),

        migrations.AddField(
            model_name="shippingrate",
            name="city",
            field=models.ForeignKey(
                to="locations.city",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="shipping_rates",
                null=True,
                blank=True,
                verbose_name="شهر",
                help_text=(
                    "خالی باشد، تعرفه برای تمام شهرهای استان "
                    "اعمال می‌شود."
                ),
            ),
        ),

        migrations.AddField(
            model_name="shippingmethod",
            name="restricted_city",
            field=models.ForeignKey(
                to="locations.city",
                on_delete=django.db.models.deletion.PROTECT,
                related_name="restricted_shipping_methods",
                null=True,
                blank=True,
                verbose_name="شهر مجاز",
                help_text=(
                    "در صورت تعیین، این روش فقط برای همین شهر "
                    "قابل انتخاب است."
                ),
            ),
        ),

        migrations.RunPython(
            forwards,
            backwards,
        ),

        migrations.RemoveField(
            model_name="shippingrate",
            name="legacy_city",
        ),

        migrations.RemoveField(
            model_name="shippingmethod",
            name="legacy_restricted_city",
        ),

        migrations.AddConstraint(
            model_name="shippingrate",
            constraint=models.UniqueConstraint(
                fields=("method", "province"),
                condition=models.Q(city__isnull=True),
                name="unique_shipping_method_province_default",
            ),
        ),

        migrations.AddConstraint(
            model_name="shippingrate",
            constraint=models.UniqueConstraint(
                fields=("method", "province", "city"),
                condition=models.Q(city__isnull=False),
                name="unique_shipping_method_province_city",
            ),
        ),
    ]
