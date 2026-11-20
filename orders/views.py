from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from .models import ShippingMethod, PROVINCE_CHOICES
from .serializers import (
    ShippingMethodSerializer,
    CreateOrderSerializer,
    OrderSerializer,
)
from django.db import transaction
from django.utils import timezone
from catalog.models import ProductVariant
from .services import cancel_locked_order
from payments.models import Payment
from .models import Order, StockReservation


@api_view(["GET"])
@permission_classes([AllowAny])
def list_provinces(request):
    return Response([{"slug": slug, "name": name} for slug, name in PROVINCE_CHOICES])


@api_view(["GET"])
@permission_classes([AllowAny])
def list_shipping_methods(request):
    province = request.query_params.get("province", "").strip()
    if not province:
        return Response({"detail": "پارامتر province الزامی است."}, status=400)

    qs = (
        ShippingMethod.objects.filter(is_active=True, rates__province=province)
        .prefetch_related("rates")
        .distinct()
        .order_by("order", "id")
    )

    serializer = ShippingMethodSerializer(qs, many=True, context={"province": province})
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_order(request):
    serializer = CreateOrderSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    order = serializer.save()
    return Response(
        {
            "success": True,
            "order_number": order.order_number,
            "total_amount": int(order.total_amount),
            "subtotal": int(order.subtotal),
            "vat_amount": int(order.vat_amount),
            "shipping_cost": int(order.shipping_cost),
        },
        status=201,
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def order_detail(request, order_number):
    try:
        order = Order.objects.prefetch_related("items").get(
            order_number=order_number, user=request.user
        )
    except Order.DoesNotExist:
        return Response({"detail": "سفارش یافت نشد."}, status=404)
    return Response(OrderSerializer(order).data)


from rest_framework.pagination import PageNumberPagination


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def my_orders(request):
    qs = Order.objects.filter(user=request.user).prefetch_related("items")
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
                {"detail": "فقط سفارش‌های در انتظار پرداخت قابل لغو هستند."},
                status=400,
            )

        variant_ids = list(
            order.stock_reservations.values_list("variant_id", flat=True)
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
        cancel_locked_order(order, reservations, now)
        Payment.objects.filter(
            order=order,
            status="pending",
        ).update(
            status="cancelled",
            gateway_response={"reason": "order_cancelled"},
        )
        return Response(
            {
                "success": True,
                "message": "سفارش با موفقیت لغو شد.",
                "order_number": order.order_number,
                "status": order.status,
            }
        )
