from rest_framework import serializers
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from catalog.models import ProductVariant
from .models import Order, OrderItem, ShippingMethod, ShippingRate


class ShippingMethodSerializer(serializers.ModelSerializer):
    cost = serializers.SerializerMethodField()

    class Meta:
        model = ShippingMethod
        fields = ["id", "name", "slug", "description", "cost"]

    def get_cost(self, obj):
        province = self.context.get("province")
        if not province:
            return None
        rate = obj.rates.filter(province=province).first()
        return int(rate.cost) if rate else None


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = [
            "product_name",
            "product_slug",
            "brand_name",
            "variant_label",
            "image_url",
            "price",
            "quantity",
            "subtotal",
        ]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    province_display = serializers.CharField(
        source="get_province_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "order_number",
            "status",
            "status_display",
            "first_name",
            "last_name",
            "mobile",
            "province",
            "province_display",
            "city",
            "address",
            "postal_code",
            "shipping_method_name",
            "shipping_cost",
            "subtotal",
            "vat_amount",
            "total_amount",
            "tracking_code",
            "notes",
            "items",
            "created_at",
        ]


class CreateOrderSerializer(serializers.Serializer):
    items = serializers.ListField(child=serializers.DictField())
    shipping_method_slug = serializers.SlugField()
    province = serializers.CharField()
    city = serializers.CharField(max_length=100)
    address = serializers.CharField(min_length=10)
    postal_code = serializers.CharField(
        max_length=10, allow_blank=True, required=False, default=""
    )
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    mobile = serializers.RegexField(r"^09\d{9}$")
    notes = serializers.CharField(allow_blank=True, required=False, default="")

    def validate(self, data):
        if not data["items"]:
            raise serializers.ValidationError({"items": "سبد خرید خالی است."})

        # Parse and validate items
        parsed = []
        variant_ids = []
        for item in data["items"]:
            try:
                vid = int(item["variant_id"])
                qty = int(item["quantity"])
            except (KeyError, ValueError, TypeError):
                raise serializers.ValidationError({"items": "داده ارسالی نامعتبر است."})
            if qty <= 0:
                raise serializers.ValidationError(
                    {"items": "تعداد باید بزرگ‌تر از صفر باشد."}
                )
            parsed.append((vid, qty))
            variant_ids.append(vid)

        variants = {
            v.id: v
            for v in ProductVariant.objects.select_related("product__brand").filter(
                id__in=variant_ids
            )
        }

        for vid, qty in parsed:
            if vid not in variants:
                raise serializers.ValidationError(
                    {"items": "محصولی در سبد شما یافت نشد."}
                )
            v = variants[vid]
            if not v.is_active or not v.product.is_active:
                raise serializers.ValidationError(
                    {"items": f"{v.product.name_fa} دیگر موجود نیست."}
                )
            if v.stock < qty:
                raise serializers.ValidationError(
                    {"items": f"موجودی {v.product.name_fa} کافی نیست."}
                )

        # Validate shipping method
        try:
            method = ShippingMethod.objects.get(
                slug=data["shipping_method_slug"], is_active=True
            )
        except ShippingMethod.DoesNotExist:
            raise serializers.ValidationError(
                {"shipping_method_slug": "روش ارسال نامعتبر است."}
            )

        rate = method.rates.filter(province=data["province"]).first()
        if not rate:
            raise serializers.ValidationError(
                {"shipping_method_slug": "این روش برای استان شما موجود نیست."}
            )

        data["_parsed"] = parsed
        data["_variants"] = variants
        data["_method"] = method
        data["_rate"] = rate
        return data

    def create(self, validated_data):
        user = self.context["request"].user
        variants = validated_data["_variants"]

        with transaction.atomic():
            # Build order items from server-side data
            subtotal = Decimal(0)
            items_data = []

            for vid, qty in validated_data["_parsed"]:
                v = variants[vid]
                item_subtotal = v.price * qty
                subtotal += item_subtotal

                primary = v.product.images.filter(is_primary=True).first()
                image_url = primary.image.url if (primary and primary.image) else ""

                label = " - ".join(filter(None, [v.flavor, v.weight, v.size, v.color]))

                items_data.append(
                    {
                        "variant": v,
                        "product_name": v.product.name_fa,
                        "product_slug": v.product.slug,
                        "brand_name": v.product.brand.name,
                        "variant_label": label,
                        "image_url": image_url,
                        "price": v.price,
                        "quantity": qty,
                        "subtotal": item_subtotal,
                    }
                )

            # Shipping cost
            free_threshold = getattr(settings, "FREE_SHIPPING_THRESHOLD", 4_000_000)
            shipping_cost = Decimal(validated_data["_rate"].cost)
            if subtotal >= free_threshold:
                shipping_cost = Decimal(0)

            # VAT
            vat_rate = getattr(settings, "VAT_RATE", 0.10)
            vat_amount = (subtotal * Decimal(str(vat_rate))).quantize(Decimal("1"))

            total = subtotal + shipping_cost + vat_amount

            order = Order.objects.create(
                user=user,
                first_name=validated_data["first_name"],
                last_name=validated_data["last_name"],
                mobile=validated_data["mobile"],
                province=validated_data["province"],
                city=validated_data["city"],
                address=validated_data["address"],
                postal_code=validated_data.get("postal_code", ""),
                shipping_method=validated_data["_method"],
                shipping_method_name=validated_data["_method"].name,
                shipping_cost=shipping_cost,
                subtotal=subtotal,
                vat_amount=vat_amount,
                total_amount=total,
                notes=validated_data.get("notes", ""),
            )

            for item in items_data:
                variant = item.pop("variant")
                OrderItem.objects.create(order=order, variant=variant, **item)
                variant.stock -= item["quantity"]
                variant.save(update_fields=["stock"])

            return order
