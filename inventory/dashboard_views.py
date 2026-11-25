from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from catalog.models import ProductVariant
from .models import InventoryDocument, InventoryDocumentLog, InventoryStockThreshold
from .services import get_variants_inventory
from . import document_services
from .serializers import InventoryDocumentCreateSerializer
from .dashboard_serializers import (
    InventoryDocumentDetailSerializer,
    InventoryDocumentListSerializer,
    InventoryDocumentLogSerializer,
)


DOCUMENT_VIEW_PERMISSIONS = (
    "inventory.can_create_inventory_document",
    "inventory.can_review_inventory_document",
    "inventory.can_approve_inventory_document",
    "inventory.can_view_inventory_reports",
)

INVENTORY_OVERVIEW_PERMISSIONS = DOCUMENT_VIEW_PERMISSIONS + (
    "inventory.can_view_inventory_reports",
)


def _require_any_permission(user, permissions):
    if not user.is_authenticated or not any(user.has_perm(p) for p in permissions):
        raise PermissionDenied("شما مجوز مشاهده اطلاعات انبار را ندارید.")


def _visible_documents(user):
    """Build document scope from explicit workflow capabilities.

    Managers have organization-wide audit visibility. Reviewers see the active
    review queue and documents on which they acted. Creators see their own
    documents in every state. Report access alone does not expose operational
    documents or their potentially sensitive cost and audit details.
    """
    qs = InventoryDocument.objects.all()
    if user.has_perm("inventory.can_approve_inventory_document"):
        return qs

    visibility = Q(pk__in=[])

    if user.has_perm("inventory.can_create_inventory_document"):
        visibility |= Q(created_by=user)

    if user.has_perm("inventory.can_review_inventory_document"):
        visibility |= Q(status="pending_review") | Q(reviewed_by=user) | Q(history__actor=user)

    if user.has_perm("inventory.can_view_inventory_reports"):
        visibility |= Q(status="approved")

    return qs.filter(visibility).distinct()


def _user_label(user):
    return user.username if user else None


def _inventory_snapshot(variants):
    inventories = get_variants_inventory(variants)
    thresholds = dict(
        InventoryStockThreshold.objects.filter(
            variant_id__in=[v.id for v in variants]
        ).values_list("variant_id", "minimum_quantity")
    )
    rows = []
    for variant in variants:
        inventory = inventories[variant.id]
        minimum = thresholds.get(variant.id, 0)
        rows.append({
            "variant_id": variant.id,
            "sku": variant.sku,
            "product_name": variant.product.name_fa,
            "brand_name": variant.product.brand.name,
            "physical": inventory["physical"],
            "reserved": inventory["reserved"],
            "available": inventory["available"],
            "minimum_quantity": minimum,
            "low_stock": inventory["available"] < minimum,
        })
    return rows


class InventoryDocumentListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = InventoryDocumentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            document = document_services.create_inventory_document(
                user=request.user,
                **serializer.validated_data,
            )
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc))
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        except InventoryDocument.DoesNotExist as exc:
            raise NotFound("Inventory document not found.") from exc

        return Response(
            {
                "id": document.id,
                "document_number": document.document_number,
                "document_type": document.document_type,
                "status": document.status,
            },
            status=status.HTTP_201_CREATED,
        )

    def get(self, request):
        _require_any_permission(request.user, DOCUMENT_VIEW_PERMISSIONS)
        queryset = _visible_documents(request.user).select_related(
            "created_by", "reviewed_by", "approved_by", "source_order"
        ).annotate(item_count=Count("items")).order_by("-created_at", "-pk")

        status_filter = request.query_params.get("status")
        type_filter = request.query_params.get("type")
        search = request.query_params.get("search", "").strip()

        valid_statuses = {value for value, _ in InventoryDocument.STATUS_CHOICES}
        valid_types = {value for value, _ in InventoryDocument.DOCUMENT_TYPES}
        if status_filter:
            if status_filter not in valid_statuses:
                raise ValidationError({"status": "وضعیت سند نامعتبر است."})
            queryset = queryset.filter(status=status_filter)
        if type_filter:
            if type_filter not in valid_types:
                raise ValidationError({"type": "نوع سند نامعتبر است."})
            queryset = queryset.filter(document_type=type_filter)
        if search:
            queryset = queryset.filter(
                Q(document_number__icontains=search)
                | Q(reference__icontains=search)
                | Q(reason__icontains=search)
                | Q(notes__icontains=search)
            )

        paginator = PageNumberPagination()
        paginator.page_size = 20
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = InventoryDocumentListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class InventoryDocumentDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, document_id):
        _require_any_permission(request.user, DOCUMENT_VIEW_PERMISSIONS)
        document = get_object_or_404(
            _visible_documents(request.user).select_related(
                "created_by", "reviewed_by", "approved_by", "source_order"
            ).prefetch_related(
                "items__variant__product__brand", "items__batch"
            ),
            pk=document_id,
        )
        return Response(InventoryDocumentDetailSerializer(document).data)


class InventoryDocumentHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, document_id):
        _require_any_permission(request.user, DOCUMENT_VIEW_PERMISSIONS)
        document = get_object_or_404(_visible_documents(request.user), pk=document_id)
        logs = InventoryDocumentLog.objects.filter(
            document=document
        ).select_related("actor").order_by("created_at", "pk")
        return Response(InventoryDocumentLogSerializer(logs, many=True).data)


class InventoryThresholdListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_any_permission(request.user, INVENTORY_OVERVIEW_PERMISSIONS)
        variants = ProductVariant.objects.select_related(
            "product", "product__brand"
        ).order_by("sku")
        rows = _inventory_snapshot(list(variants))
        return Response(rows)


class InventoryThresholdDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def put(self, request, variant_id):
        if not request.user.has_perm("inventory.can_approve_inventory_document"):
            raise PermissionDenied("فقط مدیر دارای مجوز تأیید می‌تواند حداقل موجودی را تغییر دهد.")
        value = request.data.get("minimum_quantity")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValidationError({
                "minimum_quantity": "حداقل موجودی باید عدد صحیح و بزرگ‌تر یا مساوی صفر باشد."
            })
        variant = get_object_or_404(ProductVariant, pk=variant_id)
        with transaction.atomic():
            threshold, _ = InventoryStockThreshold.objects.update_or_create(
                variant=variant,
                defaults={"minimum_quantity": value, "updated_by": request.user},
            )
        return Response({
            "variant_id": variant.id,
            "sku": variant.sku,
            "minimum_quantity": threshold.minimum_quantity,
            "updated_by": _user_label(threshold.updated_by),
            "updated_at": threshold.updated_at,
        })


class InventoryLowStockAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_any_permission(request.user, INVENTORY_OVERVIEW_PERMISSIONS)
        variants = list(
            ProductVariant.objects.select_related(
                "product", "product__brand"
            ).filter(is_active=True).order_by("sku")
        )
        rows = [
            row for row in _inventory_snapshot(variants)
            if row["minimum_quantity"] > 0 and row["low_stock"]
        ]
        return Response({"count": len(rows), "results": rows})


class InventorySummaryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        _require_any_permission(request.user, INVENTORY_OVERVIEW_PERMISSIONS)
        variants = list(
            ProductVariant.objects.select_related(
                "product", "product__brand"
            ).filter(is_active=True)
        )
        rows = _inventory_snapshot(variants)
        visible = _visible_documents(request.user)
        return Response({
            "sku_count": len(rows),
            "low_stock_count": sum(1 for row in rows if row["minimum_quantity"] > 0 and row["low_stock"]),
            "physical_quantity": sum(row["physical"] for row in rows),
            "reserved_quantity": sum(row["reserved"] for row in rows),
            "available_quantity": sum(row["available"] for row in rows),
            "pending_review_count": visible.filter(status="pending_review").count(),
            "pending_approval_count": visible.filter(status="pending_approval").count(),
            "can_manage_threshold": request.user.has_perm("inventory.can_approve_inventory_document"),
            "can_create_document": request.user.has_perm("inventory.can_create_inventory_document"),
            "can_review_document": request.user.has_perm("inventory.can_review_inventory_document"),
            "can_approve_document": request.user.has_perm("inventory.can_approve_inventory_document"),
            "can_view_reports": request.user.has_perm("inventory.can_view_inventory_reports"),
        })
