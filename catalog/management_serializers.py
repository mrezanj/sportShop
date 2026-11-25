from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from .models import Product, ProductImage, ProductVariant, ProductVariantPriceHistory


class CatalogVariantManagementSerializer(serializers.ModelSerializer):
    product = serializers.PrimaryKeyRelatedField(read_only=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=0, read_only=True)
    initial_price = serializers.DecimalField(
        max_digits=12, decimal_places=0, min_value=Decimal("1"),
        write_only=True, required=True,
    )
    sku = serializers.CharField(max_length=100, required=False, allow_blank=True)

    class Meta:
        model = ProductVariant
        fields = [
            "id", "product", "flavor", "weight", "servings", "size", "color",
            "attributes", "sku", "price", "initial_price", "shipping_weight_grams",
            "shipping_length_cm", "shipping_width_cm", "shipping_height_cm",
            "requires_special_packaging", "special_packaging_cost", "is_active",
        ]

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            fields["sku"].read_only = True
            fields["initial_price"].read_only = True
        return fields

    def validate_attributes(self, value):
        if not isinstance(value, dict) or any(
            not isinstance(key, str) or not key.strip()
            or not isinstance(item, (str, int, float, bool))
            for key, item in value.items()
        ):
            raise serializers.ValidationError(
                "ویژگی‌های سفارشی باید شیئی با کلید متنی و مقدار ساده باشند."
            )
        return value

    def validate_sku(self, value):
        value = value.strip()
        if value and ProductVariant.objects.filter(sku=value).exclude(
            pk=getattr(self.instance, "pk", None)
        ).exists():
            raise serializers.ValidationError("این SKU قبلاً ثبت شده است.")
        return value

    def validate(self, attrs):
        data = {
            field: attrs.get(field, getattr(self.instance, field, None))
            for field in ("flavor", "weight", "servings", "size", "color", "attributes")
        }
        data["attributes"] = data["attributes"] or {}
        if not isinstance(data["attributes"], dict):
            raise serializers.ValidationError({"attributes": "ساختار ویژگی‌ها نامعتبر است."})

        product = (
            self.instance.product if self.instance
            else self.context.get("product")
        )
        if product:
            candidate = ProductVariant(product=product, **data)
            fingerprint = candidate.build_variant_fingerprint()
            duplicates = ProductVariant.objects.filter(
                product=product, variant_fingerprint=fingerprint
            )
            if self.instance:
                duplicates = duplicates.exclude(pk=self.instance.pk)
            if duplicates.exists():
                raise serializers.ValidationError(
                    {"attributes": "تنوعی با همین ترکیب ویژگی‌ها برای این محصول وجود دارد."}
                )

        dimensions = [
            attrs.get(name, getattr(self.instance, name, None))
            for name in ("shipping_length_cm", "shipping_width_cm", "shipping_height_cm")
        ]
        if any(value is not None for value in dimensions) and not all(
            value is not None for value in dimensions
        ):
            raise serializers.ValidationError(
                "برای ثبت ابعاد ارسال، طول، عرض و ارتفاع باید همگی وارد شوند."
            )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        initial_price = validated_data.pop("initial_price")
        product = validated_data.pop("product")
        variant = ProductVariant.objects.create(
            product=product, price=initial_price, **validated_data
        )
        ProductVariantPriceHistory.objects.create(
            variant=variant,
            sku=variant.sku,
            product_name=product.name_fa,
            old_price=None,
            new_price=initial_price,
            change_type="initial",
            changed_by=self.context["request"].user,
            note="Initial SKU price",
        )
        return variant


class CatalogProductImageManagementSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(write_only=True, required=True)
    image_url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ProductImage
        fields = ["id", "image", "image_url", "alt_text", "is_primary", "order"]

    def get_fields(self):
        fields = super().get_fields()
        if self.instance is not None:
            fields["image"].required = False
        return fields

    def get_image_url(self, obj):
        request = self.context.get("request")
        if not obj.image:
            return None
        if request:
            return request.build_absolute_uri(obj.image.url)
        return obj.image.url

    def validate_image(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("حداکثر حجم هر تصویر ۵ مگابایت است.")
        return value
