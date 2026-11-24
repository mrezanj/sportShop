from rest_framework import serializers

from .models import ReturnRequest, ReturnRequestItem


class ReturnRequestItemSerializer(serializers.ModelSerializer):
    order_item_id = serializers.IntegerField(source="order_item_id", read_only=True)

    class Meta:
        model = ReturnRequestItem
        fields = ["order_item_id", "quantity"]


class ReturnRequestSerializer(serializers.ModelSerializer):
    items = ReturnRequestItemSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = ReturnRequest
        fields = ["id", "order_id", "reason", "status", "status_display", "staff_note", "items", "created_at", "updated_at"]
