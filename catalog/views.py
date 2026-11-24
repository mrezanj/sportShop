import csv
from pathlib import Path
from decimal import Decimal, InvalidOperation
from io import TextIOWrapper

from django.db import transaction
from django.db.models import CharField
from django.db.models.functions import Cast
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import (
    Category,
    Brand,
    Product,
    ProductVariant,
    ProductVariantPriceHistory,
)
from .serializers import (
    CategorySerializer,
    BrandSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
)
from .services import build_product_inventory_context


def _price_permission(user):
    if not user.is_superuser and not user.has_perm("catalog.can_manage_product_prices"):
        raise PermissionDenied("شما مجوز مدیریت قیمت محصولات را ندارید.")


def _apply_price_updates(rows, mode, user, note, change_type):
    if not isinstance(rows, list) or not rows:
        raise ValidationError({"items": "حداقل یک تغییر قیمت لازم است."})
    if mode not in {"fixed", "increase_percent", "decrease_percent"}:
        raise ValidationError({"mode": "نوع تغییر قیمت نامعتبر است."})

    normalized = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValidationError({"items": "ساختار ردیف قیمت نامعتبر است."})
        sku = str(row.get("sku", "")).strip()
        if not sku or sku in normalized:
            raise ValidationError({"items": "SKU خالی یا تکراری است."})
        try:
            value = Decimal(str(row.get("value")))
        except (InvalidOperation, TypeError):
            raise ValidationError({"items": f"مقدار قیمت برای {sku} نامعتبر است."})
        if not value.is_finite() or value <= 0:
            raise ValidationError({"items": f"قیمت یا درصد برای {sku} باید مثبت باشد."})
        if mode == "decrease_percent" and value > 100:
            raise ValidationError({"items": "درصد کاهش قیمت نمی‌تواند بیشتر از ۱۰۰ باشد."})
        if mode == "fixed" and value > Decimal("999999999999"):
            raise ValidationError({"items": f"قیمت SKU {sku} از محدوده مجاز بیشتر است."})
        normalized[sku] = value

    updated = []
    with transaction.atomic():
        variants = list(
            ProductVariant.objects.select_for_update()
            .select_related("product")
            .filter(sku__in=normalized)
            .order_by("id")
        )
        found = {variant.sku for variant in variants}
        missing = sorted(set(normalized) - found)
        if missing:
            raise ValidationError({"sku": "SKU یافت نشد: " + ", ".join(missing)})

        for variant in variants:
            old_price = variant.price
            value = normalized[variant.sku]
            if mode == "fixed":
                new_price = value.quantize(Decimal("1"))
            elif mode == "increase_percent":
                new_price = (old_price * (Decimal("1") + value / 100)).quantize(Decimal("1"))
            else:
                new_price = (old_price * (Decimal("1") - value / 100)).quantize(Decimal("1"))
            if new_price < 1:
                raise ValidationError({"price": f"قیمت SKU {variant.sku} نمی‌تواند کمتر از ۱ باشد."})
            if new_price > Decimal("999999999999"):
                raise ValidationError({"price": f"قیمت SKU {variant.sku} از محدوده مجاز بیشتر است."})
            if new_price == old_price:
                continue
            variant.price = new_price
            variant.save(update_fields=["price"])
            ProductVariantPriceHistory.objects.create(
                variant=variant,
                sku=variant.sku,
                product_name=variant.product.name_fa,
                old_price=old_price,
                new_price=new_price,
                change_type=change_type,
                changed_by=user,
                note=note,
            )
            updated.append({
                "sku": variant.sku,
                "old_price": int(old_price),
                "new_price": int(new_price),
            })

    return updated


class PriceManagementMixin:
    @action(
        detail=False,
        methods=["post"],
        url_path="bulk-price-update",
        permission_classes=[IsAdminUser],
    )
    def bulk_price_update(self, request):
        _price_permission(request.user)
        updated = _apply_price_updates(
            rows=request.data.get("items"),
            mode=request.data.get("mode", "fixed"),
            user=request.user,
            note=str(request.data.get("note", ""))[:500],
            change_type="bulk",
        )
        return Response({
            "success": True,
            "updated_count": len(updated),
            "items": updated,
        })

    @action(
        detail=False,
        methods=["get"],
        url_path="price-history",
        permission_classes=[IsAdminUser],
    )
    def price_history(self, request):
        _price_permission(request.user)
        queryset = ProductVariantPriceHistory.objects.select_related(
            "changed_by"
        ).order_by("-created_at", "-id")
        sku = request.query_params.get("sku", "").strip()
        if sku:
            queryset = queryset.filter(sku__icontains=sku)
        rows = list(queryset.values(
            "id",
            "sku",
            "product_name",
            "old_price",
            "new_price",
            "change_type",
            "changed_by__username",
            "note",
            "created_at",
        )[:100])
        return Response(rows)

    @action(
        detail=False,
        methods=["post"],
        url_path="import-prices",
        permission_classes=[IsAdminUser],
    )
    def import_prices(self, request):
        _price_permission(request.user)
        upload = request.FILES.get("file")
        if not upload:
            raise ValidationError({"file": "فایل CSV را انتخاب کنید."})
        if upload.size > 2 * 1024 * 1024:
            raise ValidationError({"file": "حداکثر حجم فایل ۲ مگابایت است."})

        suffix = Path(upload.name).suffix.lower()
        rows = []
        try:
            if suffix == ".csv":
                wrapper = TextIOWrapper(upload.file, encoding="utf-8-sig", newline="")
                reader = csv.DictReader(wrapper)
                if not reader.fieldnames or not {"sku", "price"}.issubset(set(reader.fieldnames)):
                    raise ValidationError({"file": "ستون‌های sku و price الزامی هستند."})
                source_rows = (
                    (index, row.get("sku"), row.get("price"))
                    for index, row in enumerate(reader, start=2)
                )
            elif suffix == ".xlsx":
                from openpyxl import load_workbook

                workbook = load_workbook(upload, read_only=True, data_only=True)
                sheet = workbook.active
                iterator = sheet.iter_rows(values_only=True)
                headers = next(iterator, None)
                if not headers:
                    raise ValidationError({"file": "فایل خالی است."})
                normalized_headers = [str(value).strip().lower() if value is not None else "" for value in headers]
                if "sku" not in normalized_headers or "price" not in normalized_headers:
                    raise ValidationError({"file": "ستون‌های sku و price الزامی هستند."})
                sku_index = normalized_headers.index("sku")
                price_index = normalized_headers.index("price")
                source_rows = (
                    (index, row[sku_index] if sku_index < len(row) else None,
                     row[price_index] if price_index < len(row) else None)
                    for index, row in enumerate(iterator, start=2)
                )
            else:
                raise ValidationError({"file": "فقط فایل‌های CSV یا XLSX پشتیبانی می‌شوند."})

            for index, raw_sku, raw_price in source_rows:
                sku = str(raw_sku or "").strip()
                try:
                    price = Decimal(str(raw_price).strip())
                except (InvalidOperation, AttributeError):
                    raise ValidationError({"file": f"قیمت ردیف {index} معتبر نیست."})
                if not sku or not price.is_finite() or price <= 0:
                    raise ValidationError({"file": f"SKU یا قیمت ردیف {index} معتبر نیست."})
                rows.append({"sku": sku, "value": str(price)})
                if len(rows) > 5000:
                    raise ValidationError({"file": "حداکثر ۵۰۰۰ ردیف مجاز است."})
        except UnicodeDecodeError as exc:
            raise ValidationError({"file": "فایل CSV باید با کدگذاری UTF-8 باشد."}) from exc

        updated = _apply_price_updates(
            rows=rows,
            mode="fixed",
            user=request.user,
            note="CSV price import",
            change_type="import",
        )
        return Response({
            "success": True,
            "updated_count": len(updated),
            "items": updated,
        })


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    lookup_field = "slug"


class BrandViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer
    lookup_field = "slug"
    filter_backends = [SearchFilter]
    search_fields = ["name"]


class ProductViewSet(PriceManagementMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_active=True).select_related(
        "brand", "category"
    ).prefetch_related("images", "variants")

    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["brand__slug", "category__slug"]
    search_fields = ["name_fa", "name_en", "brand__name"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        goal = self.request.query_params.get("consumption_goal", "").strip()
        if goal:
            queryset = queryset.annotate(
                consumption_goals_text=Cast("consumption_goals", output_field=CharField())
            ).filter(consumption_goals_text__icontains=goal)
        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        products = page if page is not None else queryset
        context = self.get_serializer_context()
        context.update(build_product_inventory_context(products))
        serializer = self.get_serializer(products, many=True, context=context)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        product = self.get_object()
        context = self.get_serializer_context()
        context.update(build_product_inventory_context([product]))
        serializer = self.get_serializer(product, context=context)
        return Response(serializer.data)
