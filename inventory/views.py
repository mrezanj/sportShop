from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from rest_framework.exceptions import NotFound
from .services import get_variants_inventory
from catalog.models import ProductVariant
from .models import InventoryDocument, InventoryDocumentItem
from .models import InventoryStockThreshold
from .permissions import CanViewInventoryReports
from .serializers import InventoryReportSerializer
from . import document_services
from .serializers import (
    InventoryDocumentCreateSerializer,
    InventoryDocumentItemCreateSerializer,
)
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError

from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated


class InventoryReportAPIView(APIView):
    permission_classes = [CanViewInventoryReports]

    def get(self, request):
        variants = list(
            ProductVariant.objects.select_related(
                "product",
                "product__brand",
            ).all()
        )

        thresholds = dict(
            InventoryStockThreshold.objects.filter(
                variant_id__in=[variant.id for variant in variants]
            ).values_list(
                "variant_id",
                "minimum_quantity",
            )
        )

        inventories = get_variants_inventory(variants)

        for variant in variants:
            inventory = inventories[variant.id]
            minimum = thresholds.get(variant.id, 0)

            variant.physical = inventory["physical"]
            variant.reserved = inventory["reserved"]
            variant.available = inventory["available"]
            variant.minimum_quantity = minimum
            variant.low_stock = inventory["available"] < minimum

        serializer = InventoryReportSerializer(
            variants,
            many=True,
        )
        return Response(serializer.data)


class InventoryDocumentCreateAPIView(APIView):
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

        return Response(
            {
                "id": document.id,
                "document_number": document.document_number,
                "document_type": document.document_type,
                "status": document.status,
            },
            status=status.HTTP_201_CREATED,
        )


class InventoryDocumentItemCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, document_id):
        serializer = InventoryDocumentItemCreateSerializer(
            data=request.data,
        )
        serializer.is_valid(raise_exception=True)

        try:
            item = document_services.add_inventory_document_item(
                user=request.user,
                document_id=document_id,
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
                "id": item.id,
                "document_id": item.document_id,
                "variant_id": item.variant_id,
                "quantity": item.quantity,
                "direction": item.direction,
                "batch_id": item.batch_id,
            },
            status=status.HTTP_201_CREATED,
        )


class InventoryDocumentItemDeleteAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, document_id, item_id):
        try:
            document_services.remove_inventory_document_item(
                user=request.user,
                document_id=document_id,
                item_id=item_id,
            )
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc))
        except DjangoValidationError as exc:
            raise ValidationError(exc.messages)
        except InventoryDocument.DoesNotExist as exc:
            raise NotFound("Inventory document not found.") from exc
        except InventoryDocumentItem.DoesNotExist as exc:
            raise NotFound("Inventory document item not found.") from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class InventoryDocumentSubmitAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, document_id):
        try:
            document = document_services.submit_inventory_document(
                user=request.user,
                document_id=document_id,
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
                "status": document.status,
            },
            status=status.HTTP_200_OK,
        )


class InventoryDocumentReviewAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, document_id):
        note = request.data.get("note", "")

        if not isinstance(note, str):
            raise ValidationError({"note": "Must be a string."})

        try:
            document = document_services.review_inventory_document(
                user=request.user,
                document_id=document_id,
                note=note,
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
                "status": document.status,
                "reviewed_by_id": document.reviewed_by_id,
                "reviewed_at": document.reviewed_at,
            },
            status=status.HTTP_200_OK,
        )


class InventoryDocumentRejectAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, document_id):
        note = request.data.get("note", "")

        if not isinstance(note, str):
            raise ValidationError({"note": "Must be a string."})

        try:
            document = document_services.reject_inventory_document(
                user=request.user,
                document_id=document_id,
                note=note,
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
                "status": document.status,
            },
            status=status.HTTP_200_OK,
        )


class InventoryDocumentApproveAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, document_id):
        note = request.data.get("note", "")

        if not isinstance(note, str):
            raise ValidationError({"note": "Must be a string."})

        try:
            document = document_services.approve_inventory_document(
                user=request.user,
                document_id=document_id,
                note=note,
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
                "status": document.status,
                "approved_by_id": document.approved_by_id,
                "approved_at": document.approved_at,
            },
            status=status.HTTP_200_OK,
        )
