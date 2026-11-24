
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



@api_view(["GET", "POST"])
@permission_classes([IsAuthenticated])
def return_requests(request):
    from .models import ReturnRequest
    from .return_services import create_return_request, ReturnRequestError
    from .return_serializers import ReturnRequestSerializer

    if request.method == "GET":
        queryset = ReturnRequest.objects.all() if request.user.has_perm("orders.can_review_return_requests") else ReturnRequest.objects.filter(user=request.user)
        queryset = queryset.prefetch_related("items")
        return Response(ReturnRequestSerializer(queryset, many=True).data)

    try:
        result = create_return_request(
            order_number=request.data.get("order_number", ""),
            user=request.user,
            reason=request.data.get("reason", ""),
            items=request.data.get("items", []),
        )
    except Order.DoesNotExist:
        return Response({"detail": "سفارش یافت نشد."}, status=404)
    except ReturnRequestError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response(ReturnRequestSerializer(result).data, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def review_return(request, request_id):
    from .return_services import review_return_request, ReturnRequestError
    from .return_serializers import ReturnRequestSerializer
    if not request.user.has_perm("orders.can_review_return_requests"):
        return Response({"detail": "اجازه بررسی درخواست مرجوعی را ندارید."}, status=403)
    from .models import ReturnRequest
    try:
        result = review_return_request(
            request_id=request_id,
            actor=request.user,
            decision=request.data.get("decision", ""),
            note=request.data.get("note", ""),
        )
    except ReturnRequest.DoesNotExist:
        return Response({"detail": "درخواست مرجوعی یافت نشد."}, status=404)
    except ReturnRequestError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response(ReturnRequestSerializer(result).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def receive_return(request, request_id):
    from .return_services import mark_return_received, ReturnRequestError
    from .return_serializers import ReturnRequestSerializer
    if not request.user.has_perm("orders.can_review_return_requests"):
        return Response({"detail": "اجازه ثبت دریافت مرجوعی را ندارید."}, status=403)
    from .models import ReturnRequest
    try:
        result = mark_return_received(
            request_id=request_id, actor=request.user, note=request.data.get("note", "")
        )
    except ReturnRequest.DoesNotExist:
        return Response({"detail": "درخواست مرجوعی یافت نشد."}, status=404)
    except ReturnRequestError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response(ReturnRequestSerializer(result).data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def open_discrepancy(request, order_number):
    from .discrepancy_services import open_order_discrepancy, DiscrepancyError
    if not request.user.has_perm("orders.can_manage_order_discrepancies"):
        return Response({"detail": "اجازه ثبت مغایرت سفارش را ندارید."}, status=403)
    try:
        order = Order.objects.get(order_number=order_number)
        case = open_order_discrepancy(
            order_id=order.pk, reason=request.data.get("reason", ""),
            actor=request.user,
        )
    except Order.DoesNotExist:
        return Response({"detail": "سفارش یافت نشد."}, status=404)
    except DiscrepancyError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response({"id": case.pk, "status": case.status, "order_number": order_number}, status=201)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def resolve_discrepancy(request, case_id):
    from .discrepancy_services import resolve_order_discrepancy, DiscrepancyError
    from .models import OrderDiscrepancy
    if not request.user.has_perm("orders.can_manage_order_discrepancies"):
        return Response({"detail": "اجازه رسیدگی به مغایرت سفارش را ندارید."}, status=403)
    try:
        case = resolve_order_discrepancy(
            case_id=case_id, resolution=request.data.get("resolution", ""),
            actor=request.user,
        )
    except OrderDiscrepancy.DoesNotExist:
        return Response({"detail": "پرونده مغایرت یافت نشد."}, status=404)
    except DiscrepancyError as exc:
        return Response({"detail": str(exc)}, status=400)
    return Response({"id": case.pk, "status": case.status, "order_status": case.order.status})



@api_view(["GET"])
@permission_classes([IsAuthenticated])
def discrepancies_list(request):
    from .models import OrderDiscrepancy
    if not request.user.has_perm("orders.can_manage_order_discrepancies"):
        return Response({"detail": "اجازه مشاهده پرونده‌های مغایرت را ندارید."}, status=403)
    queryset = OrderDiscrepancy.objects.select_related(
        "order", "opened_by", "resolved_by"
    ).order_by("-created_at")
    return Response([
        {
            "id": case.pk,
            "order_number": case.order.order_number,
            "status": case.status,
            "reason": case.reason,
            "resolution": case.resolution,
            "previous_order_status": case.previous_order_status,
            "opened_by": case.opened_by_id,
            "resolved_by": case.resolved_by_id,
            "created_at": str(case.created_at) if case.created_at else None,
            "resolved_at": str(case.resolved_at) if case.resolved_at else None,
        }
        for case in queryset
    ])
