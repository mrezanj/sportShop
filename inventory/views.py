from rest_framework.response import Response
from rest_framework.views import APIView
from .services import get_variants_inventory

from catalog.models import ProductVariant

from .models import InventoryStockThreshold
from .permissions import CanViewInventoryReports
from .serializers import InventoryReportSerializer


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
