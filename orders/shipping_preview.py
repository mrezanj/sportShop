
from datetime import timedelta
from decimal import Decimal
from django.core import signing
from django.utils import timezone

from django.conf import settings
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from catalog.models import ProductVariant
from catalog.discounts import calculate_discounts
from inventory.services import get_variants_inventory
from locations.models import City

from .models import CheckoutPriceQuote, ShippingMethod
from .shipping import ShippingCalculationError, calculate_shipping


class PreviewOrderItemSerializer(serializers.Serializer):
    variant_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1)


class ShippingPreviewSerializer(serializers.Serializer):
    items = PreviewOrderItemSerializer(many=True)
    shipping_method_slug = serializers.SlugField()
    province = serializers.CharField(max_length=30)
    city_code = serializers.CharField(max_length=10)
    discount_code = serializers.CharField(max_length=40, allow_blank=True, required=False, default="")

    def validate(self, data):
        if not data["items"]:
            raise serializers.ValidationError({
                "items": "سبد خرید خالی است."
            })

        quantities = {}

        for item in data["items"]:
            variant_id = item["variant_id"]
            quantity = item["quantity"]

            quantities[variant_id] = (
                quantities.get(variant_id, 0) + quantity
            )

        variants = list(
            ProductVariant.objects.select_related(
                "product",
            ).filter(
                id__in=quantities,
            )
        )

        if len(variants) != len(quantities):
            raise serializers.ValidationError({
                "items": "یکی از محصولات در سبد خرید یافت نشد."
            })

        variants_by_id = {
            variant.id: variant
            for variant in variants
        }

        for variant_id in quantities:
            variant = variants_by_id[variant_id]

            if not variant.is_active or not variant.product.is_active:
                raise serializers.ValidationError({
                    "items": (
                        f"محصول «{variant.product.name_fa}» "
                        "دیگر قابل سفارش نیست."
                    )
                })

        # Preview uses the official inventory ledger.
        # Final availability is rechecked during order creation.
        inventory_by_variant = get_variants_inventory(variants)

        for variant_id, quantity in quantities.items():
            variant = variants_by_id[variant_id]
            available = inventory_by_variant[variant_id]["available"]

            if available < quantity:
                raise serializers.ValidationError({
                    "items": (
                        "موجودی قابل سفارش "
                        f"{variant.product.name_fa} کافی نیست. "
                        f"موجودی قابل خرید: {available}"
                    )
                })

        city = (
            City.objects.select_related("province")
            .filter(
                code=data["city_code"],
                province__slug=data["province"],
                province__is_active=True,
                is_active=True,
            )
            .first()
        )

        if not city:
            raise serializers.ValidationError({
                "city_code": (
                    "شهر انتخاب‌شده معتبر نیست یا به استان "
                    "انتخاب‌شده تعلق ندارد."
                )
            })

        try:
            method = ShippingMethod.objects.get(
                slug=data["shipping_method_slug"],
                is_active=True,
            )
        except ShippingMethod.DoesNotExist:
            raise serializers.ValidationError({
                "shipping_method_slug": "روش ارسال نامعتبر است."
            })

        subtotal = Decimal("0")
        shipping_items = []

        for variant_id, quantity in quantities.items():
            variant = variants_by_id[variant_id]
            subtotal += variant.price * quantity
            shipping_items.append({"variant": variant, "quantity": quantity})

        discount_result = calculate_discounts(
            user=self.context["request"].user,
            variants=variants,
            quantities=quantities,
            discount_code=data.get("discount_code", ""),
        )
        discount_amount = Decimal(discount_result["discount_amount"])
        discounted_subtotal = Decimal(discount_result["discounted_subtotal"])

        try:
            shipping_result = calculate_shipping(
                method=method,
                province=data["province"],
                city=city,
                subtotal=discounted_subtotal,
                items=shipping_items,
            )
        except ShippingCalculationError as exc:
            raise serializers.ValidationError({
                "shipping_method_slug": str(exc)
            }) from exc

        vat_rate = getattr(settings, "VAT_RATE", 0.10)

        vat_amount = (
            discounted_subtotal * Decimal(str(vat_rate))
        ).quantize(Decimal("1"))

        shipping_cost = shipping_result["shipping_cost"]
        packaging_cost = shipping_result["packaging_cost"]

        total_amount = (
            discounted_subtotal + vat_amount + shipping_cost + packaging_cost
        )

        quote_payload = {
            "user_id": self.context["request"].user.pk,
            "items": [
                {"variant_id": variant_id, "quantity": quantity,
                 "sku": variants_by_id[variant_id].sku,
                 "unit_price": str(variants_by_id[variant_id].price)}
                for variant_id, quantity in sorted(quantities.items())
            ],
            "province": data["province"],
            "city_code": city.code,
            "shipping_method_slug": method.slug,
            "subtotal": int(subtotal),
            "discount_code": data.get("discount_code", "").strip().upper(),
            "discount_amount": int(discount_amount),
            "discounted_subtotal": int(discounted_subtotal),
            "discounts": discount_result["discounts"],
            "discount_lines": discount_result["lines"],
            "vat_amount": int(vat_amount),
            "shipping_cost": int(shipping_cost),
            "packaging_cost": int(packaging_cost),
            "total_amount": int(total_amount),
            "vat_rate": str(vat_rate),
            "shipping_snapshot": shipping_result["snapshot"],
            "issued_at": int(timezone.now().timestamp()),
        }
        quote_record = CheckoutPriceQuote.objects.create(
            user=self.context["request"].user,
            payload=quote_payload,
            expires_at=timezone.now() + timedelta(minutes=10),
        )
        quote_token = signing.dumps(
            {
                **quote_payload,
                "quote_id": str(quote_record.pk),
            },
            salt="orders.checkout-price-quote",
            compress=True,
        )

        data["_result"] = {
            "quote_token": quote_token,
            "items": [
                {
                    "variant_id": variant_id,
                    "sku": variants_by_id[variant_id].sku,
                    "product_name": variants_by_id[variant_id].product.name_fa,
                    "quantity": quantity,
                    "unit_price": int(variants_by_id[variant_id].price),
                    "line_subtotal": int(variants_by_id[variant_id].price * quantity),
                }
                for variant_id, quantity in sorted(quantities.items())
            ],
            "quote_expires_in": 600,
            "subtotal": int(subtotal),
            "discount_amount": int(discount_amount),
            "discounted_subtotal": int(discounted_subtotal),
            "discounts": discount_result["discounts"],
            "vat_amount": int(vat_amount),
            "shipping_cost": int(shipping_cost),
            "packaging_cost": int(packaging_cost),
            "total_amount": int(total_amount),
            "shipping": {
                "base_cost": int(
                    Decimal(
                        shipping_result["snapshot"]["base_shipping_cost"]
                    )
                ),
                "additional_weight_cost": int(
                    Decimal(
                        shipping_result["snapshot"]["additional_weight_cost"]
                    )
                ),
                "cold_shipping_cost": int(
                    Decimal(
                        shipping_result["snapshot"]["cold_shipping_cost"]
                    )
                ),
                "is_free": shipping_result["shipping_is_free"],
                "billable_weight_grams": (
                    shipping_result["shipping_billable_weight_grams"]
                ),
            },
            "packaging": {
                "raw_cost": int(
                    Decimal(
                        shipping_result["snapshot"]["raw_packaging_cost"]
                    )
                ),
                "is_free": shipping_result["packaging_is_free"],
            },
        }

        return data


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def shipping_preview(request):
    serializer = ShippingPreviewSerializer(
        data=request.data,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)

    return Response({
        "success": True,
        **serializer.validated_data["_result"],
    })
