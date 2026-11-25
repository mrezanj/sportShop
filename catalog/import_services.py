import csv
import json
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import Path

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from openpyxl import load_workbook
from rest_framework.exceptions import ValidationError

from .models import (
    Brand,
    Category,
    Product,
    ProductVariant,
    ProductVariantPriceHistory,
)

MAX_FILE_SIZE = 2 * 1024 * 1024
MAX_ROWS = 5000
REQUIRED_COLUMNS = {
    "product_slug",
    "name_fa",
    "brand_slug",
    "category_slug",
    "description",
    "price",
}
PRODUCT_TEXT_FIELDS = (
    "name_fa",
    "name_en",
    "description",
    "ingredients",
    "usage",
    "warnings",
    "contraindications",
    "medical_advice",
    "license_id",
    "authenticity_code",
    "license_details",
)
VARIANT_TEXT_FIELDS = ("flavor", "weight", "size", "color")
PRODUCT_BOOLEAN_FIELDS = ("requires_cold_shipping", "is_active")
VARIANT_BOOLEAN_FIELDS = ("requires_special_packaging", "is_active")
VARIANT_INTEGER_FIELDS = ("servings", "shipping_weight_grams")
VARIANT_DECIMAL_FIELDS = (
    "shipping_length_cm",
    "shipping_width_cm",
    "shipping_height_cm",
    "special_packaging_cost",
)


def _text(value):
    return "" if value is None else str(value).strip()


def _parse_bool(value, field_name, row_number):
    raw = _text(value).lower()
    if raw in {"1", "true", "yes", "y", "بله", "فعال"}:
        return True
    if raw in {"0", "false", "no", "n", "خیر", "غیرفعال"}:
        return False
    raise ValidationError({
        "file": f"مقدار ستون {field_name} در ردیف {row_number} باید true یا false باشد."
    })


def _parse_integer(value, field_name, row_number):
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        raise ValidationError({
            "file": f"مقدار ستون {field_name} در ردیف {row_number} باید عدد صحیح باشد."
        })
    if parsed < 0:
        raise ValidationError({
            "file": f"مقدار ستون {field_name} در ردیف {row_number} نمی‌تواند منفی باشد."
        })
    return parsed


def _parse_decimal(value, field_name, row_number):
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({
            "file": f"مقدار ستون {field_name} در ردیف {row_number} معتبر نیست."
        })
    if not parsed.is_finite() or parsed < 0:
        raise ValidationError({
            "file": f"مقدار ستون {field_name} در ردیف {row_number} باید عددی غیرمنفی باشد."
        })
    return parsed


def _parse_json(value, expected_type, field_name, row_number, default):
    raw = _text(value)
    if not raw:
        return default
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError({
            "file": f"JSON ستون {field_name} در ردیف {row_number} معتبر نیست."
        }) from exc
    if not isinstance(parsed, expected_type):
        expected = "آرایه" if expected_type is list else "شیء"
        raise ValidationError({
            "file": f"ستون {field_name} در ردیف {row_number} باید یک {expected} JSON باشد."
        })
    return parsed



def _collect_rows(rows):
    collected = []
    for row in rows:
        if len(collected) >= MAX_ROWS:
            raise ValidationError({"file": "حداکثر ۵۰۰۰ ردیف مجاز است."})
        collected.append(row)
    return collected

def _read_rows(upload):
    if not upload:
        raise ValidationError({"file": "فایل کاتالوگ را انتخاب کنید."})
    if upload.size > MAX_FILE_SIZE:
        raise ValidationError({"file": "حداکثر حجم فایل ۲ مگابایت است."})

    suffix = Path(upload.name).suffix.lower()
    raw = upload.read()
    if suffix == ".csv":
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationError({"file": "فایل CSV باید با کدگذاری UTF-8 باشد."}) from exc
        reader = csv.DictReader(StringIO(text))
        if not reader.fieldnames:
            raise ValidationError({"file": "فایل CSV سربرگ ندارد."})
        headers = [str(header or "").strip().lower() for header in reader.fieldnames]
        if len(headers) != len(set(headers)):
            raise ValidationError({"file": "نام ستون تکراری است."})
        reader.fieldnames = headers
        rows = _collect_rows(
            (
                (line_number, {key: value for key, value in row.items() if key is not None})
                for line_number, row in enumerate(reader, start=2)
            )
        )
    elif suffix == ".xlsx":
        workbook = None
        try:
            workbook = load_workbook(BytesIO(raw), read_only=True, data_only=True)
            sheet = workbook.active
            iterator = sheet.iter_rows(values_only=True)
            header_row = next(iterator, None)
            if not header_row:
                raise ValidationError({"file": "فایل Excel خالی است."})
            headers = [str(value or "").strip().lower() for value in header_row]
            if len(headers) != len(set(headers)):
                raise ValidationError({"file": "نام ستون تکراری است."})
            rows = _collect_rows(
                (
                    (line_number, {
                        headers[index]: value
                        for index, value in enumerate(values)
                        if index < len(headers)
                    })
                    for line_number, values in enumerate(iterator, start=2)
                )
            )
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError({"file": "فایل Excel قابل خواندن نیست."}) from exc
        finally:
            if workbook is not None:
                workbook.close()
    else:
        raise ValidationError({"file": "فقط فایل‌های CSV و XLSX پشتیبانی می‌شوند."})

    if not rows:
        raise ValidationError({"file": "فایل هیچ ردیف داده‌ای ندارد."})
    header_set = set(headers)
    missing = sorted(REQUIRED_COLUMNS - header_set)
    if missing:
        raise ValidationError({
            "file": "ستون‌های الزامی وجود ندارند: " + ", ".join(missing)
        })
    if "stock" in header_set:
        raise ValidationError({
            "file": "موجودی از فایل کاتالوگ وارد نمی‌شود؛ موجودی فقط از طریق اسناد انبار تغییر می‌کند."
        })
    return rows


def import_catalog_file(upload, user):
    rows = _read_rows(upload)
    normalized_rows = []
    seen_skus = set()
    seen_variant_identities = set()

    for row_number, raw in rows:
        row = {str(key).strip().lower(): value for key, value in raw.items()}
        values = {
            "row_number": row_number,
            "product_slug": _text(row.get("product_slug")),
            "name_fa": _text(row.get("name_fa")),
            "brand_slug": _text(row.get("brand_slug")),
            "category_slug": _text(row.get("category_slug")),
            "description": _text(row.get("description")),
            "price": _parse_decimal(row.get("price"), "price", row_number),
            "sku": _text(row.get("sku")),
        }
        if not all(values[key] for key in (
            "product_slug", "name_fa", "brand_slug", "category_slug", "description"
        )):
            raise ValidationError({
                "file": f"ستون‌های product_slug، name_fa، brand_slug، category_slug و description در ردیف {row_number} الزامی هستند."
            })
        if values["price"] is None or values["price"] < 1:
            raise ValidationError({
                "file": f"قیمت ردیف {row_number} باید عدد صحیح مثبت و به تومان باشد."
            })
        if values["price"] != values["price"].to_integral_value():
            raise ValidationError({
                "file": f"قیمت ردیف {row_number} باید تومان کامل و بدون اعشار باشد."
            })
        if values["sku"]:
            if values["sku"] in seen_skus:
                raise ValidationError({"file": f"SKU تکراری در فایل: {values['sku']}"})
            seen_skus.add(values["sku"])

        values["product_fields"] = {}
        for field in PRODUCT_TEXT_FIELDS:
            value = _text(row.get(field))
            if value:
                values["product_fields"][field] = value
        for field in PRODUCT_BOOLEAN_FIELDS:
            if _text(row.get(field)) != "":
                values["product_fields"][field] = _parse_bool(row[field], field, row_number)
        if _text(row.get("minimum_age")) != "":
            values["product_fields"]["minimum_age"] = _parse_integer(
                row["minimum_age"], "minimum_age", row_number
            )
        if _text(row.get("consumption_goals")):
            values["product_fields"]["consumption_goals"] = _parse_json(
                row["consumption_goals"], list, "consumption_goals", row_number, []
            )

        values["variant_fields"] = {}
        for field in VARIANT_TEXT_FIELDS:
            value = _text(row.get(field))
            if value:
                values["variant_fields"][field] = value
        for field in VARIANT_BOOLEAN_FIELDS:
            if _text(row.get(field)) != "":
                values["variant_fields"][field] = _parse_bool(row[field], field, row_number)
        for field in VARIANT_INTEGER_FIELDS:
            if _text(row.get(field)) != "":
                values["variant_fields"][field] = _parse_integer(row[field], field, row_number)
        for field in VARIANT_DECIMAL_FIELDS:
            if _text(row.get(field)) != "":
                values["variant_fields"][field] = _parse_decimal(row[field], field, row_number)
        if _text(row.get("attributes")):
            values["variant_fields"]["attributes"] = _parse_json(
                row["attributes"], dict, "attributes", row_number, {}
            )
        identity_fields = {
            "flavor": "",
            "weight": "",
            "servings": None,
            "size": "",
            "color": "",
            "attributes": {},
        }
        identity_fields.update(values["variant_fields"])
        identity = ProductVariant(**identity_fields)
        identity_key = (
            values["product_slug"],
            identity.build_variant_fingerprint(),
        )
        if identity_key in seen_variant_identities:
            raise ValidationError({
                "file": f"ترکیب ویژگی‌های تنوع در ردیف {row_number} تکراری است."
            })
        seen_variant_identities.add(identity_key)
        normalized_rows.append(values)

    created_products = set()
    updated_products = set()
    created_variants = 0
    updated_variants = 0
    price_changes = 0

    with transaction.atomic():
        brand_slugs = {row["brand_slug"] for row in normalized_rows}
        category_slugs = {row["category_slug"] for row in normalized_rows}
        brands = {
            item.slug: item
            for item in Brand.objects.select_for_update().filter(
                slug__in=brand_slugs, is_active=True
            )
        }
        categories = {
            item.slug: item
            for item in Category.objects.select_for_update().filter(
                slug__in=category_slugs, is_active=True
            )
        }

        for row in normalized_rows:
            line = row["row_number"]
            brand = brands.get(row["brand_slug"])
            category = categories.get(row["category_slug"])
            if not brand:
                raise ValidationError({
                    "file": f"برند فعال با شناسه {row['brand_slug']} در ردیف {line} پیدا نشد."
                })
            if not category:
                raise ValidationError({
                    "file": f"دسته‌بندی فعال با شناسه {row['category_slug']} در ردیف {line} پیدا نشد."
                })

            product = Product.objects.select_for_update().filter(
                slug=row["product_slug"]
            ).first()
            is_new_product = product is None
            if is_new_product:
                product = Product(
                    slug=row["product_slug"],
                    name_fa=row["name_fa"],
                    description=row["description"],
                    brand=brand,
                    category=category,
                )
            else:
                product.name_fa = row["name_fa"]
                product.description = row["description"]
                product.brand = brand
                product.category = category
            for field, value in row["product_fields"].items():
                setattr(product, field, value)
            try:
                product.full_clean()
            except DjangoValidationError as exc:
                raise ValidationError({
                    "file": f"اطلاعات محصول در ردیف {line} معتبر نیست: {exc.message_dict if hasattr(exc, 'message_dict') else exc.messages}"
                }) from exc
            product.save()
            if is_new_product:
                created_products.add(product.pk)
            else:
                updated_products.add(product.pk)

            variant = None
            if row["sku"]:
                variant = ProductVariant.objects.select_for_update().filter(
                    sku=row["sku"]
                ).first()
                if variant and variant.product_id != product.pk:
                    raise ValidationError({
                        "file": f"SKU {row['sku']} در ردیف {line} متعلق به محصول دیگری است."
                    })
            if variant is None:
                identity_fields = {
                    "flavor": "",
                    "weight": "",
                    "servings": None,
                    "size": "",
                    "color": "",
                    "attributes": {},
                }
                identity_fields.update(row["variant_fields"])
                identity = ProductVariant(product=product, **identity_fields)
                variant = ProductVariant.objects.select_for_update().filter(
                    product=product,
                    variant_fingerprint=identity.build_variant_fingerprint(),
                ).first()

            is_new_variant = variant is None
            old_price = variant.price if variant else None
            if is_new_variant:
                variant = ProductVariant(product=product)
            variant.price = row["price"]
            if row["sku"]:
                variant.sku = row["sku"]
            elif not variant.sku:
                variant._generate_sku()
            for field, value in row["variant_fields"].items():
                setattr(variant, field, value)
            try:
                variant.full_clean()
            except DjangoValidationError as exc:
                raise ValidationError({
                    "file": f"اطلاعات تنوع در ردیف {line} معتبر نیست: {exc.message_dict if hasattr(exc, 'message_dict') else exc.messages}"
                }) from exc
            variant.save()
            if is_new_variant:
                created_variants += 1
            else:
                updated_variants += 1

            if old_price is None or old_price != variant.price:
                ProductVariantPriceHistory.objects.create(
                    variant=variant,
                    sku=variant.sku,
                    product_name=product.name_fa,
                    old_price=old_price,
                    new_price=variant.price,
                    change_type="import",
                    changed_by=user,
                    note=f"ورود گروهی کاتالوگ؛ ردیف {line}",
                )
                price_changes += 1

    return {
        "success": True,
        "rows_processed": len(normalized_rows),
        "products_created": len(created_products),
        "products_updated": len(updated_products),
        "variants_created": created_variants,
        "variants_updated": updated_variants,
        "price_history_entries": price_changes,
    }
