from rest_framework import serializers

from .models import InventoryDocument, InventoryDocumentItem, InventoryDocumentLog


class InventoryDocumentListSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True, allow_null=True
    )
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, allow_null=True
    )
    approved_by_username = serializers.CharField(
        source="approved_by.username", read_only=True, allow_null=True
    )
    item_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = InventoryDocument
        fields = [
            "id", "document_number", "document_type", "status", "reference",
            "source_order_id", "reason", "notes", "created_by_type",
            "created_by_id", "created_by_username", "reviewed_by_id",
            "reviewed_by_username", "reviewed_at", "approved_by_id",
            "approved_by_username", "approved_at", "item_count",
            "created_at", "updated_at",
        ]


class InventoryDocumentItemReadSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name_fa", read_only=True)
    batch_number = serializers.CharField(
        source="batch.batch_number", read_only=True, allow_null=True
    )
    batch_status = serializers.CharField(
        source="batch.status", read_only=True, allow_null=True
    )
    batch_expiration_date = serializers.DateField(
        source="batch.expiration_date", read_only=True, allow_null=True
    )

    class Meta:
        model = InventoryDocumentItem
        fields = [
            "id", "variant_id", "sku", "product_name", "batch_id",
            "batch_number", "batch_status", "batch_expiration_date",
            "new_batch_number", "new_batch_expiration_date", "quantity",
            "direction", "unit_cost", "reason",
        ]


class InventoryDocumentDetailSerializer(InventoryDocumentListSerializer):
    items = InventoryDocumentItemReadSerializer(many=True, read_only=True)

    class Meta(InventoryDocumentListSerializer.Meta):
        fields = InventoryDocumentListSerializer.Meta.fields + ["items"]


class InventoryDocumentLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(
        source="actor.username", read_only=True, allow_null=True
    )

    class Meta:
        model = InventoryDocumentLog
        fields = [
            "id", "action", "from_status", "to_status", "actor_type",
            "actor_id", "actor_username", "note", "created_at",
        ]
