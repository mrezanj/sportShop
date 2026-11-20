from django.http import Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from catalog.models import ProductVariant
from orders.models import Order, StockReservation
from .models import Payment
from .gateways import get_gateway
from orders.services import (
    cancel_locked_order,
    transition_order_status,
)


def _lock_and_validate_reservations(order, now):
    """
    Lock variants and reservations in a consistent order.
    Return (valid, reservations, variants_by_id).
    """
    variant_ids = list(
        order.stock_reservations.values_list("variant_id", flat=True)
        .distinct()
        .order_by("variant_id")
    )

    variants = list(
        ProductVariant.objects.select_for_update()
        .filter(id__in=variant_ids)
        .order_by("id")
    )
    variants_by_id = {variant.id: variant for variant in variants}

    reservations = list(
        StockReservation.objects.select_for_update()
        .filter(order=order)
        .order_by("variant_id")
    )

    item_rows = order.items.values_list("variant_id", "quantity")
    expected = {}

    for variant_id, quantity in item_rows:
        if variant_id is None:
            return False, reservations, variants_by_id
        expected[variant_id] = expected.get(variant_id, 0) + quantity

    actual = {
        reservation.variant_id: reservation.quantity for reservation in reservations
    }

    valid = (
        order.status == "pending"
        and order.reservation_expires_at is not None
        and order.reservation_expires_at > now
        and bool(expected)
        and len(reservations) == len(expected)
        and len(variants_by_id) == len(variant_ids)
        and len(actual) == len(reservations)
        and actual == expected
    )

    if valid:
        for reservation in reservations:
            variant = variants_by_id.get(reservation.variant_id)

            if (
                reservation.status != "active"
                or reservation.expires_at <= now
                or variant is None
                or variant.stock < reservation.quantity
            ):
                valid = False
                break

    return valid, reservations, variants_by_id


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    order_number = request.data.get("order_number")

    if not order_number:
        return Response(
            {"error": "شماره سفارش الزامی است."},
            status=400,
        )
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(
                order_number=order_number, user=request.user
            )
        except Order.DoesNotExist:
            return Response({"error": "سفارش یافت نشد."}, status=404)

        if order.status == "paid":
            return Response(
                {"error": "این سفارش قبلاً پرداخت شده است."},
                status=400,
            )

        if order.status != "pending":
            return Response(
                {"error": "این سفارش قابل پرداخت نیست."},
                status=400,
            )

        now = timezone.now()
        valid, reservations, variants_by_id = _lock_and_validate_reservations(
            order, now
        )

        if not valid:
            cancel_locked_order(
                order,
                reservations,
                now,
                note="لغو خودکار به علت پایان مهلت یا نامعتبر بودن رزرو موجودی.",
            )
            return Response(
                {"error": "مهلت رزرو موجودی پایان یافته یا رزرو معتبر نیست."},
                status=400,
            )
        gateway = get_gateway()

        payment = (
            Payment.objects.select_for_update()
            .filter(order=order, status="pending")
            .order_by("-created_at")
            .first()
        )

        if not payment:
            payment = Payment.objects.create(
                order=order,
                gateway=getattr(settings, "ACTIVE_PAYMENT_GATEWAY", "mock"),
                amount=order.total_amount,
                status="pending",
            )

        gateway = get_gateway()
        result = gateway.request(payment)

        if not result.success:
            payment.status = "failed"
            payment.gateway_response = result.raw_response
            payment.save(update_fields=["status", "gateway_response"])

            return Response(
                {"error": result.message or "خطا در شروع پرداخت."},
                status=500,
            )

        payment.authority = result.authority or ""
        payment.gateway_response = result.raw_response
        payment.save(update_fields=["authority", "gateway_response"])

        return Response(
            {
                "success": True,
                "payment_id": payment.id,
                "redirect_url": result.redirect_url,
            }
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def verify_payment(request):
    order_number = request.data.get("order_number")
    status = request.data.get("status", "")
    authority = request.data.get("authority", "")

    if not order_number:
        return Response(
            {"error": "شماره سفارش الزامی است."},
            status=400,
        )

    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(
                order_number=order_number, user=request.user
            )
        except Order.DoesNotExist:
            return Response({"error": "سفارش یافت نشد."}, status=404)

        if order.status == "paid":
            return Response({"success": True, "already_paid": True})

        if order.status != "pending":
            return Response(
                {"error": "این سفارش قابل تأیید نیست."},
                status=400,
            )

        payment = (
            Payment.objects.select_for_update()
            .filter(
                order=order,
                status="pending",
                authority=authority,
            )
            .order_by("-created_at")
            .first()
        )

        if not payment:
            return Response(
                {"error": "پرداخت معتبر و در انتظار یافت نشد."},
                status=400,
            )
        if payment.amount != order.total_amount:
            payment.status = "failed"
            payment.gateway_response = {
                "reason": "payment_amount_mismatch",
            }
            payment.save(update_fields=["status", "gateway_response"])

            return Response(
                {
                    "success": False,
                    "message": "مبلغ پرداخت با مبلغ سفارش مطابقت ندارد.",
                },
                status=400,
            )
        now = timezone.now()

        valid, reservations, variants_by_id = _lock_and_validate_reservations(
            order, now
        )

        if not valid:
            cancel_locked_order(
                order,
                reservations,
                now,
                note="لغو خودکار به علت پایان مهلت یا نامعتبر بودن رزرو موجودی.",
            )
            payment.status = "cancelled"
            payment.gateway_response = {
                "reason": "reservation_expired_or_invalid",
            }
            payment.save(update_fields=["status", "gateway_response"])

            return Response(
                {
                    "success": False,
                    "message": "مهلت رزرو موجودی پایان یافته است.",
                },
                status=400,
            )

        gateway = get_gateway()
        result = gateway.verify(
            payment,
            params={
                "status": status,
                "authority": authority,
            },
        )

        if not result.success:
            payment.status = "cancelled" if status == "cancelled" else "failed"
            payment.gateway_response = result.raw_response
            payment.save(update_fields=["status", "gateway_response"])

            return Response(
                {
                    "success": False,
                    "message": result.message or "پرداخت ناموفق بود.",
                }
            )

        # Consume reservations and decrement physical stock.
        for reservation in reservations:
            variant = variants_by_id[reservation.variant_id]

            variant.stock -= reservation.quantity
            variant.save(update_fields=["stock"])

            reservation.status = "consumed"
            reservation.consumed_at = now
            reservation.save(update_fields=["status", "consumed_at"])

        payment.status = "success"
        payment.ref_id = result.ref_id or ""
        payment.paid_at = now
        payment.gateway_response = result.raw_response
        payment.save(
            update_fields=[
                "status",
                "ref_id",
                "paid_at",
                "gateway_response",
            ]
        )

        transition_order_status(
            order=order,
            new_status="paid",
            changed_by=None,
            note="پرداخت سفارش با موفقیت تأیید شد.",
        )

        return Response(
            {
                "success": True,
                "ref_id": payment.ref_id,
                "order_number": order.order_number,
            }
        )


def mock_payment_page(request, payment_id):
    """Mock bank page. Acts as the payment gateway UI."""

    if (
        not settings.DEBUG
        or getattr(settings, "ACTIVE_PAYMENT_GATEWAY", "").strip().lower() != "mock"
    ):
        raise Http404

    payment = get_object_or_404(Payment, id=payment_id)
    order = payment.order

    if payment.status != "pending" or order.status != "pending":
        return render(
            request,
            "payments/mock_already_processed.html",
            {"payment": payment, "order": order},
        )

    if request.method == "POST":
        status = request.POST.get("status", "cancelled")
        frontend_url = settings.FRONTEND_URL

        return redirect(
            f"{frontend_url}/checkout/callback"
            f"?order={order.order_number}"
            f"&status={status}"
            f"&authority={payment.authority}"
        )

    return render(
        request,
        "payments/mock_payment.html",
        {"payment": payment, "order": order},
    )
