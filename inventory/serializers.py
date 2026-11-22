from rest_framework import serializers

from catalog.models import ProductVariant
from .models import InventoryBatch, InventoryDocument


class InventoryReportSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(
        source="product.name_fa",
        read_only=True,
    )
    brand_name = serializers.CharField(
        source="product.brand.name",
        read_only=True,
    )
    minimum_quantity = serializers.IntegerField(read_only=True)
    physical = serializers.IntegerField(read_only=True)
    reserved = serializers.IntegerField(read_only=True)
    available = serializers.IntegerField(read_only=True)
    low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "sku",
            "product_name",
            "brand_name",
            "price",
            "physical",
            "reserved",
            "available",
            "minimum_quantity",
            "low_stock",
        ]


class InventoryDocumentCreateSerializer(serializers.Serializer):
    document_number = serializers.CharField(max_length=50)
    document_type = serializers.ChoiceField(
        choices=InventoryDocument.DOCUMENT_TYPES,
    )
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    reference = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default="",
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class InventoryDocumentItemCreateSerializer(serializers.Serializer):
    variant = serializers.PrimaryKeyRelatedField(
        queryset=ProductVariant.objects.all(),
    )
    quantity = serializers.IntegerField(min_value=1)
    direction = serializers.ChoiceField(
        choices=[("inbound", "Inbound"), ("outbound", "Outbound")],
    )
    batch = serializers.PrimaryKeyRelatedField(
        queryset=InventoryBatch.objects.all(),
        required=False,
        allow_null=True,
    )
    new_batch_number = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default="",
    )
    new_batch_expiration_date = serializers.DateField(
        required=False,
        allow_null=True,
    )
    unit_cost = serializers.DecimalField(
        max_digits=12,
        decimal_places=0,
        required=False,
        allow_null=True,
    )
    reason = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
    )
