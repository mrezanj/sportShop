from rest_framework import serializers

from catalog.models import ProductVariant


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