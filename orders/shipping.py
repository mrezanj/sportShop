
from decimal import Decimal, ROUND_CEILING

from locations.models import City
from .models import ShippingConfiguration, ShippingRate


class ShippingCalculationError(Exception):
    """Raised when shipping cannot be calculated safely."""


DEFAULT_VOLUMETRIC_DIVISOR = 5000
DEFAULT_FREE_SHIPPING_THRESHOLD = Decimal("4000000")
DEFAULT_FREE_PACKAGING_THRESHOLD = Decimal("5000000")


def _decimal(value):
    return Decimal(str(value or 0))


def _get_shipping_rate(method, province, city):
    city_rate = (
        ShippingRate.objects.filter(
            method=method,
            province=province,
            city=city,
        )
        .first()
    )

    if city_rate:
        if not city_rate.is_active:
            raise ShippingCalculationError(
                "ارسال با این روش برای شهر انتخاب‌شده فعال نیست."
            )
        return city_rate

    province_rate = (
        ShippingRate.objects.filter(
            method=method,
            province=province,
            city__isnull=True,
        )
        .first()
    )

    if not province_rate or not province_rate.is_active:
        raise ShippingCalculationError(
            "برای این روش ارسال و مقصد انتخاب‌شده تعرفه فعالی ثبت نشده است."
        )

    return province_rate


def _get_configuration():
    configuration, _ = ShippingConfiguration.objects.get_or_create(
        singleton_key=1,
    )

    if not configuration.is_active:
        return {
            "volumetric_divisor": DEFAULT_VOLUMETRIC_DIVISOR,
            "free_shipping_threshold": DEFAULT_FREE_SHIPPING_THRESHOLD,
            "free_packaging_threshold": DEFAULT_FREE_PACKAGING_THRESHOLD,
        }

    return {
        "volumetric_divisor": configuration.volumetric_divisor,
        "free_shipping_threshold": _decimal(
            configuration.free_shipping_threshold
        ),
        "free_packaging_threshold": _decimal(
            configuration.free_packaging_threshold
        ),
    }


def _calculate_volumetric_weight(variant, divisor):
    dimensions = (
        variant.shipping_length_cm,
        variant.shipping_width_cm,
        variant.shipping_height_cm,
    )

    if all(value is None for value in dimensions):
        return 0

    if any(value is None for value in dimensions):
        raise ShippingCalculationError(
            f"ابعاد بسته‌بندی محصول «{variant.product.name_fa}» ناقص است."
        )

    volume = (
        _decimal(variant.shipping_length_cm)
        * _decimal(variant.shipping_width_cm)
        * _decimal(variant.shipping_height_cm)
    )

    return int(
        (volume / Decimal(divisor)).to_integral_value(
            rounding=ROUND_CEILING
        )
    )


def calculate_shipping(
    *,
    method,
    province,
    city,
    subtotal,
    items,
):
    """
    Calculate shipping and special packaging from trusted database data.

    Each item must contain:
        {
            "variant": ProductVariant instance,
            "quantity": positive integer,
        }

    city must be an active City instance.

    Returns calculated amounts and immutable item snapshots.
    """

    if not items:
        raise ShippingCalculationError("سبد خرید خالی است.")

    if not isinstance(city, City) or not city.pk:
        raise ShippingCalculationError(
            "شهر مقصد برای محاسبه ارسال معتبر نیست."
        )

    if not city.is_active or not city.province.is_active:
        raise ShippingCalculationError(
            "شهر یا استان انتخاب‌شده فعال نیست."
        )

    if city.province.slug != province:
        raise ShippingCalculationError(
            "شهر انتخاب‌شده متعلق به استان مقصد نیست."
        )

    if not method.is_active:
        raise ShippingCalculationError(
            "روش ارسال انتخاب‌شده فعال نیست."
        )

    if method.restricted_province and method.restricted_province != province:
        raise ShippingCalculationError(
            "این روش ارسال برای استان انتخاب‌شده قابل استفاده نیست."
        )

    if (
        method.restricted_city_id
        and method.restricted_city_id != city.pk
    ):
        raise ShippingCalculationError(
            "این روش ارسال فقط برای شهر مشخص‌شده قابل استفاده است."
        )

    if (
        method.restricted_city_id
        and method.restricted_city.province.slug != province
    ):
        raise ShippingCalculationError(
            "محدودیت شهر این روش ارسال با استان آن سازگار نیست."
        )

    configuration = _get_configuration()

    rate = _get_shipping_rate(
        method,
        province,
        city,
    )

    divisor = configuration["volumetric_divisor"]

    if divisor <= 0:
        raise ShippingCalculationError(
            "ضریب محاسبه وزن حجمی معتبر نیست."
        )

    actual_weight = 0
    volumetric_weight = 0
    packaging_cost = Decimal("0")
    requires_cold_shipping = False
    item_snapshots = []

    for item in items:
        variant = item["variant"]
        quantity = int(item["quantity"])

        if quantity <= 0:
            raise ShippingCalculationError(
                "تعداد محصولات برای محاسبه ارسال نامعتبر است."
            )

        unit_weight = variant.shipping_weight_grams

        if unit_weight is None or unit_weight <= 0:
            raise ShippingCalculationError(
                f"وزن قابل ارسال محصول «{variant.product.name_fa}» ثبت نشده است."
            )

        unit_volumetric_weight = _calculate_volumetric_weight(
            variant,
            divisor,
        )

        actual_weight += unit_weight * quantity
        volumetric_weight += unit_volumetric_weight * quantity

        item_requires_cold = variant.product.requires_cold_shipping
        item_requires_packaging = variant.requires_special_packaging

        unit_packaging_cost = (
            _decimal(variant.special_packaging_cost)
            if item_requires_packaging
            else Decimal("0")
        )

        packaging_cost += unit_packaging_cost * quantity
        requires_cold_shipping = (
            requires_cold_shipping or item_requires_cold
        )

        item_snapshots.append(
            {
                "variant": variant,
                "quantity": quantity,
                "shipping_weight_grams": unit_weight,
                "shipping_length_cm": variant.shipping_length_cm,
                "shipping_width_cm": variant.shipping_width_cm,
                "shipping_height_cm": variant.shipping_height_cm,
                "requires_cold_shipping": item_requires_cold,
                "requires_special_packaging": item_requires_packaging,
                "special_packaging_cost": unit_packaging_cost,
            }
        )

    billable_weight = max(actual_weight, volumetric_weight)

    included_weight = rate.included_weight_grams
    additional_weight_step = rate.additional_weight_step_grams

    if included_weight <= 0 or additional_weight_step <= 0:
        raise ShippingCalculationError(
            "تنظیمات وزن تعرفه ارسال معتبر نیست."
        )

    additional_steps = 0

    if billable_weight > included_weight:
        extra_weight = billable_weight - included_weight

        additional_steps = int(
            (
                Decimal(extra_weight)
                / Decimal(additional_weight_step)
            ).to_integral_value(rounding=ROUND_CEILING)
        )

    base_shipping_cost = _decimal(rate.cost)

    additional_weight_cost = (
        Decimal(additional_steps)
        * _decimal(rate.additional_weight_cost)
    )

    cold_shipping_cost = (
        _decimal(rate.cold_shipping_cost)
        if requires_cold_shipping
        else Decimal("0")
    )

    raw_shipping_cost = (
        base_shipping_cost
        + additional_weight_cost
        + cold_shipping_cost
    )

    subtotal = _decimal(subtotal)

    shipping_is_free = (
        subtotal >= configuration["free_shipping_threshold"]
    )

    packaging_is_free = (
        subtotal >= configuration["free_packaging_threshold"]
    )

    final_shipping_cost = (
        Decimal("0")
        if shipping_is_free
        else raw_shipping_cost
    )

    final_packaging_cost = (
        Decimal("0")
        if packaging_is_free
        else packaging_cost
    )

    snapshot = {
        "method_id": method.id,
        "method_name": method.name,
        "rate_id": rate.id,
        "province": province,
        "province_name": city.province.name,
        "city_id": city.id,
        "city_code": city.code,
        "city": city.name,
        "city_name": city.name,
        "county_name": city.county_name,
        "district_name": city.district_name,
        "volumetric_divisor": divisor,
        "actual_weight_grams": actual_weight,
        "volumetric_weight_grams": volumetric_weight,
        "billable_weight_grams": billable_weight,
        "included_weight_grams": included_weight,
        "additional_weight_step_grams": additional_weight_step,
        "additional_weight_steps": additional_steps,
        "base_shipping_cost": str(base_shipping_cost),
        "additional_weight_cost": str(additional_weight_cost),
        "cold_shipping_cost": str(cold_shipping_cost),
        "raw_shipping_cost": str(raw_shipping_cost),
        "shipping_is_free": shipping_is_free,
        "final_shipping_cost": str(final_shipping_cost),
        "raw_packaging_cost": str(packaging_cost),
        "packaging_is_free": packaging_is_free,
        "final_packaging_cost": str(final_packaging_cost),
        "free_shipping_threshold": str(
            configuration["free_shipping_threshold"]
        ),
        "free_packaging_threshold": str(
            configuration["free_packaging_threshold"]
        ),
        "requires_cold_shipping": requires_cold_shipping,
    }

    return {
        "rate": rate,
        "shipping_cost": final_shipping_cost,
        "packaging_cost": final_packaging_cost,
        "shipping_actual_weight_grams": actual_weight,
        "shipping_volumetric_weight_grams": volumetric_weight,
        "shipping_billable_weight_grams": billable_weight,
        "shipping_is_free": shipping_is_free,
        "packaging_is_free": packaging_is_free,
        "snapshot": snapshot,
        "item_snapshots": item_snapshots,
    }
