from rest_framework import serializers, viewsets
from rest_framework.permissions import BasePermission

from .models import DiscountCampaign


class CanManageDiscounts(BasePermission):
    message = "شما مجوز مدیریت کمپین‌های تخفیف را ندارید."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_superuser
                or user.has_perm("catalog.can_manage_product_prices")
            )
        )


class DiscountCampaignSerializer(serializers.ModelSerializer):
    class Meta:
        model = DiscountCampaign
        fields = [
            "id", "name", "code", "scope", "product", "category", "brand",
            "discount_type", "value", "maximum_discount_amount",
            "minimum_order_amount", "starts_at", "ends_at", "priority",
            "is_stackable", "first_purchase_only", "max_uses",
            "per_user_limit", "usage_count", "is_active", "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "usage_count", "created_at", "updated_at"]

    def validate(self, attrs):
        campaign = self.instance or DiscountCampaign()
        for field, value in attrs.items():
            setattr(campaign, field, value)
        campaign.clean()
        return attrs


class DiscountCampaignViewSet(viewsets.ModelViewSet):
    queryset = DiscountCampaign.objects.select_related(
        "product", "category", "brand"
    ).all()
    serializer_class = DiscountCampaignSerializer
    pagination_class = None
    permission_classes = [CanManageDiscounts]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        serializer.save()
