from rest_framework import serializers
from .models import Category, Brand, Product, ProductImage, ProductVariant


class CategorySerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "slug", "parent", "image_url"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ["id", "name", "slug", "logo", "description"]


class ProductImageSerializer(serializers.ModelSerializer):
    image_url = serializers.SerializerMethodField()

    class Meta:
        model = ProductImage
        fields = ["id", "image_url", "alt_text", "is_primary", "order"]

    def get_image_url(self, obj):
        request = self.context.get("request")
        if obj.image and request:
            return request.build_absolute_uri(obj.image.url)
        return None


class ProductVariantSerializer(serializers.ModelSerializer):
    stock = serializers.SerializerMethodField()

    class Meta:
        model = ProductVariant
        fields = [
            "id",
            "flavor",
            "weight",
            "servings",
            "size",
            "color",
            "sku",
            "price",
            "stock",
            "is_active",
        ]

    def get_stock(self, obj):
        inventory = self.context.get("variant_inventory", {})
        variant_data = inventory.get(obj.pk, {})
        return variant_data.get("available", 0)


class ProductListSerializer(serializers.ModelSerializer):
    """نسخه سبک برای لیست محصولات - فقط اطلاعات ضروری"""

    brand = BrandSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    primary_image = serializers.SerializerMethodField()
    min_price = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name_fa",
            "name_en",
            "slug",
            "brand",
            "category",
            "primary_image",
            "min_price",
            "requires_cold_shipping",
            "minimum_age",
            "created_at",
        ]

    def get_primary_image(self, obj):
        primary = next(
            (image for image in obj.images.all() if image.is_primary),
            None,
        )
        if primary and primary.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(primary.image.url)
        return None

    def get_min_price(self, obj):
        inventory = self.context.get("variant_inventory", {})

        active_variants = [
            variant for variant in obj.variants.all() if variant.is_active
        ]

        available_variants = [
            variant
            for variant in active_variants
            if inventory.get(variant.pk, {}).get("available", 0) > 0
        ]

        variants = available_variants or active_variants
        prices = [variant.price for variant in variants]

        return min(prices) if prices else None


class ProductDetailSerializer(serializers.ModelSerializer):
    """نسخه کامل برای صفحه محصول"""

    brand = BrandSerializer(read_only=True)
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "name_fa",
            "name_en",
            "slug",
            "brand",
            "category",
            "description",
            "ingredients",
            "usage",
            "warnings",
            "requires_cold_shipping",
            "minimum_age",
            "images",
            "variants",
            "created_at",
            "updated_at",
        ]
