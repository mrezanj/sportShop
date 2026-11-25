from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .import_services import import_inventory_file


class InventoryBulkImportAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        document_number = request.data.get("document_number")
        if not isinstance(document_number, str) or not document_number.strip():
            raise ValidationError({"document_number": "شماره سند الزامی است."})
        try:
            result = import_inventory_file(
                user=request.user,
                upload=request.FILES.get("file"),
                document_number=document_number.strip(),
                reference=request.data.get("reference", ""),
                reason=request.data.get("reason", "ورود گروهی موجودی"),
            )
        except DjangoPermissionDenied as exc:
            raise PermissionDenied(str(exc)) from exc
        except DjangoValidationError as exc:
            if hasattr(exc, "message_dict"):
                raise ValidationError(exc.message_dict) from exc
            raise ValidationError(exc.messages) from exc
        return Response(result, status=status.HTTP_201_CREATED)
