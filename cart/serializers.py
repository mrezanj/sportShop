
from rest_framework import serializers

from .models import Cart, CartItem
from catalog.models import ProductVariant


class AddCartItemSerializer(serializers.Serializer):
    variant_id = serializers.PrimaryKeyRelatedField(
        source="variant",
        queryset=ProductVariant.objects.select_related("product").filter(
            is_active=True,
            product__is_active=True,
        ),
    )
    quantity = serializers.IntegerField(min_value=1)

    def validate_quantity(self, value):
        if value < 1:
            raise serializers.ValidationError(
                "تعداد باید حداقل یک باشد."
            )
        return value


class UpdateCartItemSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)


class CartItemSerializer(serializers.ModelSerializer):
    variant_id = serializers.IntegerField(
        source="variant.id",
        read_only=True,
    )
    product_name = serializers.CharField(
        source="variant.product.name_fa",
        read_only=True,
    )
    product_slug = serializers.CharField(
        source="variant.product.slug",
        read_only=True,
    )
    brand_name = serializers.CharField(
        source="variant.product.brand.name",
        read_only=True,
    )
    sku = serializers.CharField(
        source="variant.sku",
        read_only=True,
    )
    price = serializers.DecimalField(
        source="variant.price",
        max_digits=12,
        decimal_places=0,
        read_only=True,
    )
    subtotal = serializers.SerializerMethodField()
    variant_label = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = [
            "id",
            "variant_id",
            "product_name",
            "product_slug",
            "brand_name",
            "variant_label",
            "sku",
            "price",
            "quantity",
            "subtotal",
            "image_url",
        ]

    def get_subtotal(self, obj):
        return obj.subtotal

    def get_variant_label(self, obj):
        variant = obj.variant

        return " - ".join(
            filter(
                None,
                [
                    variant.flavor,
                    variant.weight,
                    variant.size,
                    variant.color,
                ],
            )
        )

    def get_image_url(self, obj):
        request = self.context.get("request")
        primary = obj.variant.product.images.filter(
            is_primary=True
        ).first()

        if primary and primary.image and request:
            return request.build_absolute_uri(primary.image.url)

        return None


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total_quantity = serializers.IntegerField(read_only=True)
    subtotal = serializers.DecimalField(
        max_digits=14,
        decimal_places=0,
        read_only=True,
    )

    class Meta:
        model = Cart
        fields = [
            "id",
            "items",
            "total_quantity",
            "subtotal",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
