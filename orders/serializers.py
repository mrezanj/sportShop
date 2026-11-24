
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from catalog.models import ProductVariant
from inventory.services import (
    allocate_stock_reservation,
    get_variants_inventory,
)
from locations.models import City
from .models import (
    Order,
    OrderItem,
    ShippingMethod,
    ShippingRate,
    StockReservation,
    OrderStatusHistory,
)
from .shipping import (
    ShippingCalculationError,
    calculate_shipping,
)


class ShippingMethodSerializer(serializers.ModelSerializer):
    cost = serializers.SerializerMethodField()

    class Meta:
        model = ShippingMethod
        fields = ["id", "name", "slug", "description", "cost"]

    def get_cost(self, obj):
        province = self.context.get("province")
        city = self.context.get("city")

        if not province or not city:
            return None

        city_rate = obj.rates.filter(
            province=province,
            city=city,
        ).first()

        if city_rate:
            return int(city_rate.cost) if city_rate.is_active else None

        province_rate = obj.rates.filter(
            province=province,
            city__isnull=True,
        ).first()

        if province_rate and province_rate.is_active:
            return int(province_rate.cost)

        return None


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
        source="get_province_display",
        read_only=True,
    )
    status_display = serializers.CharField(
        source="get_status_display",
        read_only=True,
    )

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
            "packaging_cost",
            "shipping_actual_weight_grams",
            "shipping_volumetric_weight_grams",
            "shipping_billable_weight_grams",
            "shipping_is_free",
            "packaging_is_free",
            "subtotal",
            "vat_amount",
            "total_amount",
            "tracking_code",
            "notes",
            "items",
            "created_at",
        ]


class CreateOrderSerializer(serializers.Serializer):
    items = serializers.ListField(
        child=serializers.DictField(),
    )
    shipping_method_slug = serializers.SlugField()
    province = serializers.CharField(max_length=30)
    city_code = serializers.CharField(max_length=10)
    address = serializers.CharField(min_length=10)
    postal_code = serializers.CharField(
        max_length=10,
        allow_blank=True,
        required=False,
        default="",
    )
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100)
    mobile = serializers.RegexField(r"^09\d{9}$")
    notes = serializers.CharField(
        allow_blank=True,
        required=False,
        default="",
    )
    quote_token = serializers.CharField(write_only=True, max_length=10000)

    def validate(self, data):
        if not data["items"]:
            raise serializers.ValidationError(
                {"items": "سبد خرید خالی است."}
            )

        try:
            price_quote = signing.loads(
                data["quote_token"],
                salt="orders.checkout-price-quote",
                max_age=600,
            )
        except signing.BadSignature:
            raise serializers.ValidationError({
                "quote_token": "پیش‌نمایش قیمت منقضی یا نامعتبر است؛ دوباره محاسبه کنید."
            })

        request = self.context.get("request")
        if not request or price_quote.get("user_id") != request.user.pk:
            raise serializers.ValidationError({
                "quote_token": "پیش‌نمایش قیمت متعلق به این کاربر نیست."
            })

        quantities = {}

        for item in data["items"]:
            try:
                variant_id = int(item["variant_id"])
                quantity = int(item["quantity"])
            except (KeyError, ValueError, TypeError):
                raise serializers.ValidationError(
                    {"items": "داده ارسالی نامعتبر است."}
                )

            if variant_id <= 0 or quantity <= 0:
                raise serializers.ValidationError(
                    {"items": "شناسه و تعداد باید بزرگ‌تر از صفر باشند."}
                )

            quantities[variant_id] = (
                quantities.get(variant_id, 0) + quantity
            )

        variants = ProductVariant.objects.select_related(
            "product__brand"
        ).filter(id__in=quantities)

        if variants.count() != len(quantities):
            raise serializers.ValidationError(
                {"items": "محصولی در سبد شما یافت نشد."}
            )

        for variant in variants:
            if not variant.is_active or not variant.product.is_active:
                raise serializers.ValidationError(
                    {
                        "items": (
                            f"{variant.product.name_fa} دیگر موجود نیست."
                        )
                    }
                )

        restricted_variants = [
            variant
            for variant in variants
            if variant.product.minimum_age is not None
        ]

        if restricted_variants:
            request = self.context.get("request")
            user = getattr(request, "user", None)
            user_profile = getattr(user, "profile", None)
            birth_date = getattr(user_profile, "birth_date", None)

            if not birth_date:
                raise serializers.ValidationError(
                    {
                        "items": (
                            "برای خرید این محصول، ابتدا تاریخ تولد "
                            "خود را در پروفایل ثبت کنید."
                        )
                    }
                )

            today = timezone.localdate()
            age = (
                today.year
                - birth_date.year
                - (
                    (today.month, today.day)
                    < (birth_date.month, birth_date.day)
                )
            )

            for variant in restricted_variants:
                minimum_age = variant.product.minimum_age

                if age < minimum_age:
                    raise serializers.ValidationError(
                        {
                            "items": (
                                f"سن شما برای خرید "
                                f"{variant.product.name_fa} کافی نیست. "
                                f"حداقل سن مجاز: {minimum_age} سال."
                            )
                        }
                    )

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
            raise serializers.ValidationError(
                {
                    "city_code": (
                        "شهر انتخاب‌شده معتبر نیست یا به استان "
                        "انتخاب‌شده تعلق ندارد."
                    )
                }
            )

        try:
            method = ShippingMethod.objects.get(
                slug=data["shipping_method_slug"],
                is_active=True,
            )
        except ShippingMethod.DoesNotExist:
            raise serializers.ValidationError(
                {
                    "shipping_method_slug": "روش ارسال نامعتبر است."
                }
            )

        quoted_items = {
            int(item["variant_id"]): int(item["quantity"])
            for item in price_quote.get("items", [])
        }
        if quoted_items != quantities:
            raise serializers.ValidationError({
                "quote_token": "سبد خرید پس از محاسبه قیمت تغییر کرده است؛ دوباره محاسبه کنید."
            })
        if (
            price_quote.get("province") != data["province"]
            or price_quote.get("city_code") != city.code
            or price_quote.get("shipping_method_slug") != method.slug
        ):
            raise serializers.ValidationError({
                "quote_token": "اطلاعات ارسال پس از محاسبه قیمت تغییر کرده است؛ دوباره محاسبه کنید."
            })

        data["_price_quote"] = price_quote
        data["_quantities"] = quantities
        data["_method"] = method
        data["_city"] = city

        return data

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user
        quantities = validated_data["_quantities"]
        method = validated_data["_method"]
        city = validated_data["_city"]
        price_quote = validated_data["_price_quote"]
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

            variants_by_id = {
                variant.id: variant
                for variant in variants
            }

            # Recheck quoted SKU and price while variant rows are locked.
            quoted_by_id = {
                int(item["variant_id"]): item
                for item in price_quote["items"]
            }
            for variant_id, quantity in quantities.items():
                variant = variants_by_id[variant_id]
                quoted = quoted_by_id.get(variant_id)
                if (
                    not quoted
                    or int(quoted["quantity"]) != quantity
                    or quoted["sku"] != variant.sku
                    or Decimal(quoted["unit_price"]) != variant.price
                ):
                    raise serializers.ValidationError({
                        "price_changed": (
                            f"قیمت یا مشخصات {variant.product.name_fa} تغییر کرده است؛ "
                            "پیش‌نمایش جدید را بررسی و تأیید کنید."
                        )
                    })

            # Recheck product availability after acquiring locks.
            for variant_id in quantities:
                variant = variants_by_id[variant_id]

                if not variant.is_active or not variant.product.is_active:
                    raise serializers.ValidationError(
                        {
                            "items": (
                                f"{variant.product.name_fa} دیگر موجود نیست."
                            )
                        }
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

            for variant_id, quantity in quantities.items():
                variant = variants_by_id[variant_id]
                available = inventory_by_variant[variant_id]["available"]

                if available < quantity:
                    raise serializers.ValidationError(
                        {
                            "items": (
                                "موجودی قابل سفارش "
                                f"{variant.product.name_fa} کافی نیست. "
                                f"موجودی قابل خرید: {available}"
                            )
                        }
                    )

            # Build order items using trusted database data.
            subtotal = Decimal("0")
            items_data = []
            shipping_items = []

            for variant_id, quantity in quantities.items():
                variant = variants_by_id[variant_id]
                item_subtotal = variant.price * quantity
                subtotal += item_subtotal

                primary = variant.product.images.filter(
                    is_primary=True
                ).first()

                image_url = (
                    primary.image.url
                    if primary and primary.image
                    else ""
                )

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
                        "quantity": quantity,
                        "subtotal": item_subtotal,
                    }
                )

                shipping_items.append(
                    {
                        "variant": variant,
                        "quantity": quantity,
                    }
                )

            # Calculate shipping and packaging from trusted product data.
            try:
                shipping_result = calculate_shipping(
                    method=method,
                    province=validated_data["province"],
                    city=city,
                    subtotal=subtotal,
                    items=shipping_items,
                )
            except ShippingCalculationError as exc:
                raise serializers.ValidationError(
                    {"shipping_method_slug": str(exc)}
                ) from exc

            shipping_snapshot = shipping_result["snapshot"]

            item_snapshots_by_variant = {
                snapshot["variant"].id: snapshot
                for snapshot in shipping_result["item_snapshots"]
            }

            # VAT calculation remains based on the products subtotal.
            vat_rate = getattr(settings, "VAT_RATE", 0.10)
            vat_amount = (
                subtotal * Decimal(str(vat_rate))
            ).quantize(Decimal("1"))

            shipping_cost = shipping_result["shipping_cost"]
            packaging_cost = shipping_result["packaging_cost"]

            quoted_totals = {
                "subtotal": int(subtotal),
                "vat_amount": int(vat_amount),
                "shipping_cost": int(shipping_cost),
                "packaging_cost": int(packaging_cost),
                "total_amount": int(
                    subtotal + shipping_cost + packaging_cost + vat_amount
                ),
            }
            for field, current_value in quoted_totals.items():
                if price_quote.get(field) != current_value:
                    raise serializers.ValidationError({
                        "price_changed": (
                            "مبلغ نهایی سفارش تغییر کرده است؛ پیش‌نمایش جدید را "
                            "بررسی و دوباره تأیید کنید."
                        )
                    })

            total = (
                subtotal
                + shipping_cost
                + packaging_cost
                + vat_amount
            )

            order = Order.objects.create(
                user=user,
                first_name=validated_data["first_name"],
                last_name=validated_data["last_name"],
                mobile=validated_data["mobile"],
                province=validated_data["province"],
                city=city.name,
                address=validated_data["address"],
                postal_code=validated_data.get("postal_code", ""),
                shipping_method=method,
                shipping_method_name=method.name,
                shipping_cost=shipping_cost,
                packaging_cost=packaging_cost,
                shipping_actual_weight_grams=(
                    shipping_result["shipping_actual_weight_grams"]
                ),
                shipping_volumetric_weight_grams=(
                    shipping_result["shipping_volumetric_weight_grams"]
                ),
                shipping_billable_weight_grams=(
                    shipping_result["shipping_billable_weight_grams"]
                ),
                shipping_is_free=shipping_result["shipping_is_free"],
                packaging_is_free=shipping_result["packaging_is_free"],
                shipping_calculation_snapshot=shipping_snapshot,
                subtotal=subtotal,
                vat_amount=vat_amount,
                discount_amount=0,
                pricing_snapshot={
                    "version": 1,
                    "quoted_at": price_quote.get("issued_at"),
                    "items": [
                        {
                            "variant_id": item["variant_id"],
                            "sku": item["sku"],
                            "product_name": variants_by_id[int(item["variant_id"])].product.name_fa,
                            "quantity": item["quantity"],
                            "unit_price": item["unit_price"],
                            "discount_amount": "0",
                            "line_subtotal": str(
                                variants_by_id[int(item["variant_id"])].price
                                * int(item["quantity"])
                            ),
                        }
                        for item in price_quote["items"]
                    ],
                    "subtotal": str(subtotal),
                    "vat_rate": str(vat_rate),
                    "vat_amount": str(vat_amount),
                    "shipping_cost": str(shipping_cost),
                    "packaging_cost": str(packaging_cost),
                    "discount_amount": "0",
                    "total_amount": str(total),
                },
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

                shipping_item = item_snapshots_by_variant[variant.id]

                OrderItem.objects.create(
                    order=order,
                    variant=variant,
                    **item,
                    shipping_weight_grams=(
                        shipping_item["shipping_weight_grams"]
                    ),
                    shipping_length_cm=(
                        shipping_item["shipping_length_cm"]
                    ),
                    shipping_width_cm=(
                        shipping_item["shipping_width_cm"]
                    ),
                    shipping_height_cm=(
                        shipping_item["shipping_height_cm"]
                    ),
                    requires_cold_shipping=(
                        shipping_item["requires_cold_shipping"]
                    ),
                    requires_special_packaging=(
                        shipping_item["requires_special_packaging"]
                    ),
                    special_packaging_cost=(
                        shipping_item["special_packaging_cost"]
                    ),
                )

                reservation = StockReservation.objects.create(
                    order=order,
                    variant=variant,
                    quantity=quantity,
                    expires_at=expires_at,
                )

                try:
                    allocate_stock_reservation(
                        reservation,
                        now=now,
                    )
                except DjangoValidationError as exc:
                    raise serializers.ValidationError(
                        {"items": str(exc)}
                    ) from exc

            return order
