import csv
import zipfile
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
    _require_permission,
)
from .models import InventoryBatch

MAX_FILE_SIZE = 2 * 1024 * 1024
MAX_ROWS = 5000
MAX_XLSX_UNCOMPRESSED_SIZE = 20 * 1024 * 1024
MAX_XLSX_ENTRIES = 1000
REQUIRED_COLUMNS = {"sku", "quantity", "batch_number"}


def _text(value):
    return "" if value is None else str(value).strip()


def _normalize_headers(values):
    headers = [_text(value).lower() for value in values]
    if not headers or any(not header for header in headers):
        raise ValidationError({"file": "همه ستون‌ها باید نام داشته باشند."})
    if len(headers) != len(set(headers)):
        raise ValidationError({"file": "نام ستون تکراری است."})
    missing = sorted(REQUIRED_COLUMNS - set(headers))
    if missing:
        raise ValidationError({"file": "ستون‌های الزامی وجود ندارند: " + ", ".join(missing)})
    return headers


def _append_row(rows, line, values, headers):
    values = list(values)
    if len(values) > len(headers) and any(_text(value) for value in values[len(headers):]):
        raise ValidationError({"file": f"تعداد سلول‌های ردیف {line} از تعداد ستون‌های سربرگ بیشتر است."})
    values = values[:len(headers)]
    values.extend([None] * (len(headers) - len(values)))
    if not any(_text(value) for value in values):
        return
    if len(rows) >= MAX_ROWS:
        raise ValidationError({"file": f"حداکثر {MAX_ROWS} ردیف داده مجاز است."})
    rows.append((line, dict(zip(headers, values))))


def _validate_xlsx_archive(raw):
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            entries = archive.infolist()
            if len(entries) > MAX_XLSX_ENTRIES:
                raise ValidationError({"file": "ساختار فایل Excel بیش از حد پیچیده است."})
            if sum(entry.file_size for entry in entries) > MAX_XLSX_UNCOMPRESSED_SIZE:
                raise ValidationError({"file": "حجم بازشده فایل Excel بیش از حد مجاز است."})
    except zipfile.BadZipFile as exc:
        raise ValidationError({"file": "فایل Excel معتبر نیست."}) from exc


def _read_rows(upload):
    if upload is None:
        raise ValidationError({"file": "فایل موجودی را انتخاب کنید."})
    if upload.size > MAX_FILE_SIZE:
        raise ValidationError({"file": "حداکثر حجم فایل ۲ مگابایت است."})

    suffix = Path(upload.name).suffix.lower()
    raw = upload.read()
    rows = []

    if suffix == ".csv":
        try:
            decoded = raw.decode("utf-8-sig")
            reader = csv.reader(StringIO(decoded))
            header = next(reader, None)
            if not header:
                raise ValidationError({"file": "فایل CSV سربرگ ندارد."})
            headers = _normalize_headers(header)
            for line, values in enumerate(reader, start=2):
                if line > MAX_ROWS + 1:
                    raise ValidationError({"file": f"حداکثر {MAX_ROWS} ردیف داده مجاز است."})
                _append_row(rows, line, values, headers)
        except UnicodeDecodeError as exc:
            raise ValidationError({"file": "فایل CSV باید با کدگذاری UTF-8 باشد."}) from exc
        except csv.Error as exc:
            raise ValidationError({"file": "ساختار فایل CSV معتبر نیست."}) from exc

    elif suffix == ".xlsx":
        _validate_xlsx_archive(raw)
        workbook = None
        try:
            workbook = load_workbook(
                BytesIO(raw),
                read_only=True,
                data_only=True,
                keep_links=False,
            )
            iterator = workbook.active.iter_rows(values_only=True)
            header = next(iterator, None)
            if not header:
                raise ValidationError({"file": "فایل Excel خالی است."})
            headers = _normalize_headers(header)
            for line, values in enumerate(iterator, start=2):
                if line > MAX_ROWS + 1:
                    raise ValidationError({"file": f"حداکثر {MAX_ROWS} ردیف داده مجاز است."})
                _append_row(rows, line, values, headers)
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
    try:
        parsed = Decimal(_text(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({"file": f"تعداد ردیف {line} باید عدد صحیح باشد."}) from exc
    if not parsed.is_finite() or parsed <= 0 or parsed != parsed.to_integral_value():
        raise ValidationError({"file": f"تعداد ردیف {line} باید عدد صحیح بزرگ‌تر از صفر باشد."})
    return int(parsed)


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
    _require_permission(user, "inventory.can_create_inventory_document")
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
