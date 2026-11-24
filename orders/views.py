
from django.db import transaction
from django.utils import timezone

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination

from catalog.models import ProductVariant
from locations.models import City
from payments.models import Payment

from .models import (
    ShippingMethod,
    PROVINCE_CHOICES,
    Order,
    StockReservation,
)
from .serializers import (
    ShippingMethodSerializer,
    CreateOrderSerializer,
    OrderSerializer,
)
from .services import cancel_locked_order


@api_view(["GET"])
@permission_classes([AllowAny])
def list_provinces(request):
    return Response([
        {"slug": slug, "name": name}
        for slug, name in PROVINCE_CHOICES
    ])


@api_view(["GET"])
@permission_classes([AllowAny])
def list_shipping_methods(request):
    province = request.query_params.get("province", "").strip()
    city_code = request.query_params.get("city_code", "").strip()

    if not province:
        return Response(
            {"detail": "پارامتر province الزامی است."},
            status=400,
        )

    if not city_code:
        return Response(
            {"detail": "پارامتر city_code الزامی است."},
            status=400,
        )

    city = (
        City.objects.select_related("province")
        .filter(
            code=city_code,
            province__slug=province,
            province__is_active=True,
            is_active=True,
        )
        .first()
    )

    if not city:
        return Response(
            {
                "detail": (
                    "شهر انتخاب‌شده معتبر نیست یا به استان "
                    "انتخاب‌شده تعلق ندارد."
                )
            },
            status=400,
        )

    methods = (
        ShippingMethod.objects.filter(is_active=True)
        .prefetch_related("rates")
        .order_by("order", "id")
    )

    available_methods = []

    for method in methods:
        if (
            method.restricted_province
            and method.restricted_province != province
        ):
            continue

        if (
            method.restricted_city_id
            and method.restricted_city_id != city.id
        ):
            continue

        city_rate = next(
            (
                rate
                for rate in method.rates.all()
                if rate.province == province
                and rate.city_id == city.id
            ),
            None,
        )

        if city_rate:
            if not city_rate.is_active:
                continue
        else:
            province_rate = next(
                (
                    rate
                    for rate in method.rates.all()
                    if rate.province == province
                    and rate.city_id is None
                ),
                None,
            )

            if not province_rate or not province_rate.is_active:
                continue

        available_methods.append(method)

    serializer = ShippingMethodSerializer(
        available_methods,
        many=True,
        context={
            "province": province,
            "city": city,
        },
    )

    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_order(request):
    serializer = CreateOrderSerializer(
        data=request.data,
        context={"request": request},
    )
    serializer.is_valid(raise_exception=True)
    order = serializer.save()

    return Response(
        {
            "success": True,
            "order_number": order.order_number,
            "total_amount": int(order.total_amount),
            "subtotal": int(order.subtotal),
            "vat_amount": int(order.vat_amount),
            "discount_amount": int(order.discount_amount),
            "shipping_cost": int(order.shipping_cost),
        },
        status=201,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_detail(request, order_number):
    try:
        order = Order.objects.prefetch_related("items").get(
            order_number=order_number,
            user=request.user,
        )
    except Order.DoesNotExist:
        return Response(
            {"detail": "سفارش یافت نشد."},
            status=404,
        )

    return Response(OrderSerializer(order).data)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_orders(request):
    qs = (
        Order.objects.filter(user=request.user)
        .prefetch_related("items")
    )

    paginator = PageNumberPagination()
    paginator.page_size = 20

    page = paginator.paginate_queryset(qs, request)
    serializer = OrderSerializer(page, many=True)

    return paginator.get_paginated_response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def cancel_order(request, order_number):
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(
                order_number=order_number,
                user=request.user,
            )
        except Order.DoesNotExist:
            return Response(
                {"detail": "سفارش یافت نشد."},
                status=404,
            )

        if order.status != "pending":
            return Response(
                {
                    "detail": (
                        "فقط سفارش‌های در انتظار پرداخت "
                        "قابل لغو هستند."
                    )
                },
                status=400,
            )

        unresolved_payment_exists = Payment.objects.filter(
            order=order,
            status__in=[
                "initiating",
                "verifying",
                "unknown",
                "pending",
            ],
        ).exists()

        if unresolved_payment_exists:
            return Response(
                {
                    "detail": (
                        "این سفارش دارای پرداخت تعیین‌تکلیف‌نشده است. "
                        "تا مشخص‌شدن وضعیت پرداخت، امکان لغو سفارش "
                        "وجود ندارد."
                    )
                },
                status=409,
            )

        variant_ids = list(
            order.stock_reservations.values_list(
                "variant_id",
                flat=True,
            )
            .distinct()
            .order_by("variant_id")
        )

        list(
            ProductVariant.objects.select_for_update()
            .filter(id__in=variant_ids)
            .order_by("id")
        )

        reservations = list(
            StockReservation.objects.select_for_update()
            .filter(order=order)
            .order_by("variant_id")
        )

        now = timezone.now()

        cancel_locked_order(
            order,
            reservations,
            now,
            changed_by=request.user,
            note="لغو سفارش به درخواست مشتری.",
        )

        return Response(
            {
                "success": True,
                "message": "سفارش با موفقیت لغو شد.",
                "order_number": order.order_number,
                "status": order.status,
            }
        )
