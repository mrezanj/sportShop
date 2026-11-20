from rest_framework import serializers
from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(
        source='get_status_display', read_only=True
    )

    class Meta:
        model = Payment
        fields = [
            'id', 'order', 'gateway', 'amount', 'status', 'status_display',
            'authority', 'ref_id', 'created_at', 'paid_at',
        ]
        read_only_fields = fields