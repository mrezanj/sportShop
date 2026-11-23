from rest_framework import serializers
from decimal import Decimal
from django.conf import settings
from django.db import transaction
from catalog.models import ProductVariant
from datetime import timedelta
from django.utils import timezone
from django.db.models import Sum
from .models import (
    Order,
    OrderItem,
    ShippingMethod,
    ShippingRate,
    StockReservation,
    OrderStatusHistory,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from inventory.services import allocate_stock_reservation, get_variants_inventory


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

        quantities = {}

        for item in data["items"]:
            try:
                vid = int(item["variant_id"])
                qty = int(item["quantity"])
            except (KeyError, ValueError, TypeError):
                raise serializers.ValidationError({"items": "داده ارسالی نامعتبر است."})

            if vid <= 0 or qty <= 0:
                raise serializers.ValidationError(
                    {"items": "شناسه و تعداد باید بزرگ‌تر از صفر باشند."}
                )

            quantities[vid] = quantities.get(vid, 0) + qty

        variants = ProductVariant.objects.select_related("product__brand").filter(
            id__in=quantities
        )

        if variants.count() != len(quantities):
            raise serializers.ValidationError({"items": "محصولی در سبد شما یافت نشد."})

        for variant in variants:
            if not variant.is_active or not variant.product.is_active:
                raise serializers.ValidationError(
                    {"items": f"{variant.product.name_fa} دیگر موجود نیست."}
                )

        try:
            method = ShippingMethod.objects.get(
                slug=data["shipping_method_slug"],
                is_active=True,
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

        data["_quantities"] = quantities
        data["_method"] = method
        data["_rate"] = rate

        return data

    def create(self, validated_data):
        user = self.context["request"].user
        quantities = validated_data["_quantities"]
        now = timezone.now()

        reservation_minutes = getattr(
            settings,
            "STOCK_RESERVATION_MINUTES",
            30,
        )
        expires_at = now + timedelta(minutes=reservation_minutes)

        with transaction.atomic():
            # Lock variants in a consistent order to prevent overselling.
            variants = list(
                ProductVariant.objects.select_for_update()
                .select_related("product__brand")
                .filter(id__in=quantities)
                .order_by("id")
            )

            if len(variants) != len(quantities):
                raise serializers.ValidationError(
                    {"items": "یکی از محصولات دیگر در دسترس نیست."}
                )

            variants_by_id = {variant.id: variant for variant in variants}

            # Recheck product availability after acquiring locks.
            for variant_id, qty in quantities.items():
                variant = variants_by_id[variant_id]

                if not variant.is_active or not variant.product.is_active:
                    raise serializers.ValidationError(
                        {"items": f"{variant.product.name_fa} دیگر موجود نیست."}
                    )

            variant_ids = list(quantities.keys())

            # Mark old active reservations as expired.
            StockReservation.objects.filter(
                variant_id__in=variant_ids,
                status="active",
                expires_at__lte=now,
            ).update(
                status="expired",
                released_at=now,
            )

            # Validate availability using one grouped inventory snapshot.
            inventory_by_variant = get_variants_inventory(
                variants,
                now=now,
            )

            for variant_id, qty in quantities.items():
                variant = variants_by_id[variant_id]
                available = inventory_by_variant[variant_id]["available"]

                if available < qty:
                    raise serializers.ValidationError(
                        {
                            "items": (
                                f"موجودی قابل سفارش "
                                f"{variant.product.name_fa} کافی نیست. "
                                f"موجودی قابل خرید: {available}"
                            )
                        }
                    )

            # Build order items from server-side data.
            subtotal = Decimal(0)
            items_data = []

            for variant_id, qty in quantities.items():
                variant = variants_by_id[variant_id]
                item_subtotal = variant.price * qty
                subtotal += item_subtotal

                primary = variant.product.images.filter(is_primary=True).first()

                image_url = primary.image.url if primary and primary.image else ""

                label = " - ".join(
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

                items_data.append(
                    {
                        "variant": variant,
                        "product_name": variant.product.name_fa,
                        "product_slug": variant.product.slug,
                        "brand_name": variant.product.brand.name,
                        "variant_label": label,
                        "image_url": image_url,
                        "price": variant.price,
                        "quantity": qty,
                        "subtotal": item_subtotal,
                    }
                )

            # Shipping cost.
            free_threshold = getattr(
                settings,
                "FREE_SHIPPING_THRESHOLD",
                4_000_000,
            )

            shipping_cost = Decimal(validated_data["_rate"].cost)

            if subtotal >= free_threshold:
                shipping_cost = Decimal(0)

            # VAT.
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
                reservation_expires_at=expires_at,
            )
            OrderStatusHistory.objects.create(
                order=order,
                old_status="",
                new_status="pending",
                changed_by=user,
                note="ایجاد سفارش توسط مشتری.",
            )
            for item in items_data:
                variant = item.pop("variant")
                quantity = item["quantity"]

                OrderItem.objects.create(
                    order=order,
                    variant=variant,
                    **item,
                )

                reservation = StockReservation.objects.create(
                    order=order,
                    variant=variant,
                    quantity=quantity,
                    expires_at=expires_at,
                )

                try:
                    allocate_stock_reservation(reservation, now=now)
                except DjangoValidationError as exc:
                    raise serializers.ValidationError({"items": str(exc)}) from exc

            return order
