from django.db.models import Prefetch, Q
from django.utils import timezone
from django.utils.dateparse import parse_date

from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .dashboard_serializers import _person_info
from .dashboard_views import DOCUMENT_VIEW_PERMISSIONS, _require_any_permission
from .models import InventoryBatch, InventoryDocument, InventoryMovement
from .services import get_variants_batch_inventory


class InventoryReportPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class InventoryBatchReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_any_permission(request.user, DOCUMENT_VIEW_PERMISSIONS)

        queryset = InventoryBatch.objects.select_related(
            "variant",
            "variant__product",
            "variant__product__brand",
            "created_by",
            "created_by__profile",
        ).prefetch_related(
            Prefetch(
                "movements",
                queryset=InventoryMovement.objects.filter(
                    movement_type="inbound"
                ).select_related(
                    "document",
                    "document__created_by",
                    "document__created_by__profile",
                ).order_by("created_at", "pk"),
                to_attr="report_inbound_movements",
            )
        ).order_by("variant__sku", "expiration_date", "pk")

        search = request.query_params.get("search", "").strip()
        status_filter = request.query_params.get("status", "").strip()
        valid_statuses = {value for value, _ in InventoryBatch.STATUS_CHOICES}

        if status_filter:
            if status_filter not in valid_statuses:
                raise ValidationError({"status": "وضعیت بچ نامعتبر است."})
            queryset = queryset.filter(status=status_filter)

        if search:
            queryset = queryset.filter(
                Q(batch_number__icontains=search)
                | Q(variant__sku__icontains=search)
                | Q(variant__product__name_fa__icontains=search)
                | Q(variant__product__brand__name__icontains=search)
            )

        paginator = InventoryReportPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        today = timezone.localdate()
        batch_quantities = get_variants_batch_inventory(
            {batch.variant_id for batch in page},
            today=today,
        )
        rows = []

        for batch in page:
            quantities = batch_quantities.get(
                batch.id,
                {"physical": 0, "reserved": 0},
            )
            physical = quantities["physical"]
            reserved = quantities["reserved"]
            available = (
                max(physical - reserved, 0)
                if batch.status == "available"
                and not (batch.expiration_date and batch.expiration_date < today)
                else 0
            )
            created_by_display, created_by_role = _person_info(batch.created_by)
            source_document = next(
                (
                    movement.document
                    for movement in batch.report_inbound_movements
                    if movement.document.created_by_id
                ),
                None,
            )
            document_creator_display, document_creator_role = _person_info(
                source_document.created_by if source_document else None
            )
            rows.append({
                "id": batch.id,
                "variant_id": batch.variant_id,
                "sku": batch.variant.sku,
                "product_name": batch.variant.product.name_fa,
                "brand_name": batch.variant.product.brand.name,
                "batch_number": batch.batch_number,
                "expiration_date": batch.expiration_date,
                "status": batch.status,
                "status_display": batch.get_status_display(),
                "is_expired": bool(
                    batch.expiration_date and batch.expiration_date < today
                ),
                "physical": physical,
                "reserved": reserved,
                "available": available,
                "created_by_display": created_by_display,
                "created_by_role": created_by_role,
                "document_created_by_display": document_creator_display,
                "document_created_by_role": document_creator_role,
                "created_at": batch.created_at,
            })

        return paginator.get_paginated_response(rows)


class InventoryMovementReportAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_any_permission(request.user, DOCUMENT_VIEW_PERMISSIONS)

        queryset = InventoryMovement.objects.select_related(
            "batch",
            "batch__variant",
            "batch__variant__product",
            "batch__variant__product__brand",
            "document",
            "document_item",
            "document__created_by",
            "document__created_by__profile",
            "created_by",
            "created_by__profile",
        ).order_by("-created_at", "-pk")

        search = request.query_params.get("search", "").strip()
        movement_type = request.query_params.get("movement_type", "").strip()
        batch_id = request.query_params.get("batch_id", "").strip()
        document_number = request.query_params.get("document_number", "").strip()
        from_date_value = request.query_params.get("from_date", "").strip()
        to_date_value = request.query_params.get("to_date", "").strip()

        valid_movement_types = {
            value for value, _ in InventoryMovement.MOVEMENT_TYPES
        }
        if movement_type:
            if movement_type not in valid_movement_types:
                raise ValidationError({
                    "movement_type": "نوع گردش نامعتبر است."
                })
            queryset = queryset.filter(movement_type=movement_type)

        if batch_id:
            try:
                parsed_batch_id = int(batch_id)
                if parsed_batch_id <= 0:
                    raise ValueError
            except ValueError:
                raise ValidationError({"batch_id": "شناسه بچ نامعتبر است."})
            queryset = queryset.filter(batch_id=parsed_batch_id)

        if document_number:
            queryset = queryset.filter(
                document__document_number__icontains=document_number
            )

        if search:
            queryset = queryset.filter(
                Q(batch__batch_number__icontains=search)
                | Q(batch__variant__sku__icontains=search)
                | Q(batch__variant__product__name_fa__icontains=search)
                | Q(document__document_number__icontains=search)
                | Q(notes__icontains=search)
            )

        from_date = None
        to_date = None
        if from_date_value:
            from_date = parse_date(from_date_value)
            if from_date is None:
                raise ValidationError({"from_date": "تاریخ شروع نامعتبر است."})
            queryset = queryset.filter(created_at__date__gte=from_date)
        if to_date_value:
            to_date = parse_date(to_date_value)
            if to_date is None:
                raise ValidationError({"to_date": "تاریخ پایان نامعتبر است."})
            queryset = queryset.filter(created_at__date__lte=to_date)
        if from_date and to_date and from_date > to_date:
            raise ValidationError({
                "date": "تاریخ شروع نباید بعد از تاریخ پایان باشد."
            })

        paginator = InventoryReportPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        movement_labels = dict(InventoryMovement.MOVEMENT_TYPES)
        document_type_labels = dict(InventoryDocument.DOCUMENT_TYPES)
        document_status_labels = dict(InventoryDocument.STATUS_CHOICES)
        rows = []

        for movement in page:
            actor_display, actor_role = _person_info(movement.created_by)
            if movement.created_by_type == "system":
                actor_display = "سیستم"
            document_creator_display, document_creator_role = _person_info(
                movement.document.created_by
            )
            rows.append({
                "id": movement.id,
                "batch_id": movement.batch_id,
                "batch_number": movement.batch.batch_number,
                "sku": movement.batch.variant.sku,
                "product_name": movement.batch.variant.product.name_fa,
                "movement_type": movement.movement_type,
                "movement_type_display": movement_labels.get(
                    movement.movement_type, movement.movement_type
                ),
                "quantity_delta": movement.quantity_delta,
                "document_id": movement.document_id,
                "document_number": movement.document.document_number,
                "document_type": movement.document.document_type,
                "document_type_display": document_type_labels.get(
                    movement.document.document_type,
                    movement.document.document_type,
                ),
                "document_status": movement.document.status,
                "document_status_display": document_status_labels.get(
                    movement.document.status, movement.document.status
                ),
                "document_item_id": movement.document_item_id,
                "unit_cost": movement.document_item.unit_cost,
                "created_by_display": actor_display,
                "created_by_role": actor_role,
                "document_created_by_display": document_creator_display,
                "document_created_by_role": document_creator_role,
                "created_at": movement.created_at,
                "notes": movement.notes,
            })

        return paginator.get_paginated_response(rows)
