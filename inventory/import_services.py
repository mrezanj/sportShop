import csv
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO, StringIO
from pathlib import Path

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook

from catalog.models import ProductVariant
from .document_services import (
    add_inventory_document_item,
    create_inventory_document,
)
from .models import InventoryBatch

MAX_FILE_SIZE = 2 * 1024 * 1024
MAX_ROWS = 5000
REQUIRED_COLUMNS = {"sku", "quantity", "batch_number"}


def _text(value):
    return "" if value is None else str(value).strip()


def _read_rows(upload):
    if upload is None:
        raise ValidationError({"file": "فایل موجودی را انتخاب کنید."})
    if upload.size > MAX_FILE_SIZE:
        raise ValidationError({"file": "حداکثر حجم فایل ۲ مگابایت است."})

    suffix = Path(upload.name).suffix.lower()
    raw = upload.read()
    if suffix == ".csv":
        try:
            decoded = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValidationError({"file": "فایل CSV باید با کدگذاری UTF-8 باشد."}) from exc
        reader = csv.DictReader(StringIO(decoded))
        if not reader.fieldnames:
            raise ValidationError({"file": "فایل CSV سربرگ ندارد."})
        headers = [_text(value).lower() for value in reader.fieldnames]
        if len(headers) != len(set(headers)):
            raise ValidationError({"file": "نام ستون تکراری است."})
        reader.fieldnames = headers
        rows = [
            (line, {key: value for key, value in row.items() if key is not None})
            for line, row in enumerate(reader, start=2)
        ]
    elif suffix == ".xlsx":
        workbook = None
        try:
            workbook = load_workbook(BytesIO(raw), read_only=True, data_only=True)
            iterator = workbook.active.iter_rows(values_only=True)
            header = next(iterator, None)
            if not header:
                raise ValidationError({"file": "فایل Excel خالی است."})
            headers = [_text(value).lower() for value in header]
            if len(headers) != len(set(headers)):
                raise ValidationError({"file": "نام ستون تکراری است."})
            rows = [
                (line, {headers[index]: value for index, value in enumerate(values) if index < len(headers)})
                for line, values in enumerate(iterator, start=2)
            ]
        except ValidationError:
            raise
        except Exception as exc:
            raise ValidationError({"file": "فایل Excel قابل خواندن نیست."}) from exc
        finally:
            if workbook is not None:
                workbook.close()
    else:
        raise ValidationError({"file": "فقط فایل‌های CSV و XLSX پشتیبانی می‌شوند."})

    rows = [(line, row) for line, row in rows if any(_text(value) for value in row.values())]
    if not rows:
        raise ValidationError({"file": "فایل هیچ ردیف داده‌ای ندارد."})
    if len(rows) > MAX_ROWS:
        raise ValidationError({"file": f"حداکثر {MAX_ROWS} ردیف داده مجاز است."})
    missing = sorted(REQUIRED_COLUMNS - set(headers))
    if missing:
        raise ValidationError({"file": "ستون‌های الزامی وجود ندارند: " + ", ".join(missing)})
    return rows


def _parse_date(value, line):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = _text(value)
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError({"file": f"تاریخ انقضای ردیف {line} باید با قالب YYYY-MM-DD باشد."}) from exc


def _parse_quantity(value, line):
    raw = _text(value)
    try:
        parsed = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"file": f"تعداد ردیف {line} باید عدد صحیح باشد."}) from exc
    if parsed <= 0:
        raise ValidationError({"file": f"تعداد ردیف {line} باید بزرگ‌تر از صفر باشد."})
    return parsed


def _parse_unit_cost(value, line):
    if value in (None, ""):
        return None
    try:
        parsed = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({"file": f"بهای واحد ردیف {line} معتبر نیست."}) from exc
    if not parsed.is_finite() or parsed < 0 or parsed != parsed.to_integral_value():
        raise ValidationError({"file": f"بهای واحد ردیف {line} باید عدد صحیح غیرمنفی به تومان باشد."})
    return parsed


@transaction.atomic
def import_inventory_file(*, user, upload, document_number, reference="", reason="ورود گروهی موجودی"):
    rows = _read_rows(upload)
    normalized = []
    seen = set()
    skus = set()

    for line, raw in rows:
        row = {str(key).strip().lower(): value for key, value in raw.items()}
        sku = _text(row.get("sku"))
        batch_number = _text(row.get("batch_number"))
        if not sku or not batch_number:
            raise ValidationError({"file": f"SKU و شماره بچ در ردیف {line} الزامی است."})
        key = (sku, batch_number)
        if key in seen:
            raise ValidationError({"file": f"SKU و شماره بچ در ردیف {line} تکراری است."})
        seen.add(key)
        skus.add(sku)
        normalized.append({
            "line": line,
            "sku": sku,
            "quantity": _parse_quantity(row.get("quantity"), line),
            "batch_number": batch_number,
            "expiration_date": _parse_date(row.get("expiration_date"), line),
            "unit_cost": _parse_unit_cost(row.get("unit_cost"), line),
            "reason": _text(row.get("reason")),
        })

    variants = {
        variant.sku: variant
        for variant in ProductVariant.objects.select_for_update().filter(sku__in=skus).order_by("id")
    }
    missing_skus = sorted(skus - set(variants))
    if missing_skus:
        raise ValidationError({"file": "SKUهای زیر در سیستم پیدا نشدند: " + ", ".join(missing_skus)})

    today = timezone.localdate()
    for row in normalized:
        if row["expiration_date"] and row["expiration_date"] < today:
            raise ValidationError({"file": f"تاریخ انقضای ردیف {row['line']} در گذشته است."})
        batch = InventoryBatch.objects.select_for_update().filter(
            variant=variants[row["sku"]],
            batch_number=row["batch_number"],
        ).first()
        if batch:
            if batch.status != "available":
                raise ValidationError({"file": f"بچ {row['batch_number']} در ردیف {row['line']} قابل استفاده نیست."})
            if batch.expiration_date and batch.expiration_date < today:
                raise ValidationError({"file": f"بچ {row['batch_number']} منقضی شده است."})
            if row["expiration_date"] and batch.expiration_date != row["expiration_date"]:
                raise ValidationError({"file": f"تاریخ انقضای بچ موجود در ردیف {row['line']} با فایل مطابقت ندارد."})
            row["batch"] = batch
        else:
            row["batch"] = None

    document = create_inventory_document(
        user=user,
        document_number=document_number,
        document_type="purchase",
        reference=reference,
        reason=reason,
        notes=f"ورود گروهی از فایل؛ {len(normalized)} ردیف",
    )

    for row in normalized:
        add_inventory_document_item(
            user=user,
            document_id=document.id,
            variant=variants[row["sku"]],
            quantity=row["quantity"],
            direction="inbound",
            batch=row["batch"],
            new_batch_number="" if row["batch"] else row["batch_number"],
            new_batch_expiration_date=None if row["batch"] else row["expiration_date"],
            unit_cost=row["unit_cost"],
            reason=row["reason"],
        )

    return {
        "success": True,
        "document_id": document.id,
        "document_number": document.document_number,
        "status": document.status,
        "rows_processed": len(normalized),
    }
