from django.shortcuts import get_object_or_404, render, redirect
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseBadRequest
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from catalog.models import ProductVariant
from orders.models import Order, StockReservation
from .models import Payment, MockGatewayTransaction
from .gateways import get_gateway
from .gateways.base import PaymentResult
from inventory.sale_services import record_order_sale
from orders.services import (
    cancel_locked_order,
    transition_order_status,
)
from datetime import timedelta

# Maximum time to wait before considering an operation stale.
PAYMENT_OPERATION_TIMEOUT = timedelta(minutes=2)


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
            ):
                valid = False
                break

    return valid, reservations, variants_by_id


def _complete_successful_payment(
    order,
    payment,
    reservations,
    now,
    result,
):
    """Complete a verified payment while holding the required database locks."""
    try:
        with transaction.atomic():
            record_order_sale(
                order,
                reservations=reservations,
                now=now,
            )
    except ValidationError:
        payment.status = "unknown"
        payment.gateway_response = {
            **(result.raw_response or {}),
            "step": "verify",
            "reason": "inventory_sale_failed",
            "outcome_unknown": True,
        }
        payment.save(
            update_fields=[
                "status",
                "gateway_response",
            ]
        )
        return False

    payment.status = "success"
    payment.ref_id = result.ref_id or ""
    payment.paid_at = now
    payment.gateway_response = result.raw_response or {}
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
    return True


def _get_recovery_operation(payment):
    if payment.status == "initiating":
        return "request", payment.request_started_at

    if payment.status != "unknown":
        return None, None

    step = (payment.gateway_response or {}).get("step")

    if step == "request":
        return "request", payment.request_started_at

    if step == "verify":
        return "verify", payment.verification_started_at

    return None, None


def _can_claim_recovery(payment, now):
    operation, started_at = _get_recovery_operation(payment)

    if operation is None or started_at is None:
        return False, "recovery_not_supported"

    if now - started_at < PAYMENT_OPERATION_TIMEOUT:
        return False, "operation_not_stale"

    if (
        payment.inquiry_started_at is not None
        and now - payment.inquiry_started_at < PAYMENT_OPERATION_TIMEOUT
    ):
        return False, "inquiry_in_progress"

    return True, None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    order_number = request.data.get("order_number")

    if not order_number:
        return Response(
            {"error": "شماره سفارش الزامی است."},
            status=400,
        )

    # Resolve gateway configuration before creating a payment attempt.
    gateway = get_gateway()

    # Phase 1: Validate and claim the payment attempt in a short transaction.
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(
                order_number=order_number,
                user=request.user,
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

        payment = (
            Payment.objects.select_for_update()
            .filter(
                order=order,
                status__in=["initiating", "unknown", "pending"],
            )
            .order_by("-created_at", "-id")
            .first()
        )

        if payment:
            if payment.status in ["initiating", "unknown"]:
                return Response(
                    {
                        "success": False,
                        "error": (
                            "وضعیت درخواست پرداخت هنوز مشخص نیست. "
                            "لطفاً از ارسال درخواست مجدد خودداری کنید."
                        ),
                        "payment_id": payment.id,
                    },
                    status=409,
                )

            redirect_url = (payment.gateway_response or {}).get("redirect_url")

            if payment.authority and redirect_url:
                return Response(
                    {
                        "success": True,
                        "payment_id": payment.id,
                        "redirect_url": redirect_url,
                    }
                )

            return Response(
                {
                    "success": False,
                    "error": (
                        "اطلاعات درخواست پرداخت ناقص است. "
                        "لطفاً با پشتیبانی تماس بگیرید."
                    ),
                    "payment_id": payment.id,
                },
                status=409,
            )

        payment = Payment.objects.create(
            order=order,
            gateway=getattr(settings, "ACTIVE_PAYMENT_GATEWAY", "mock"),
            amount=order.total_amount,
            status="initiating",
            request_started_at=now,
        )

        payment_id = payment.id
        order_id = order.id
        request_key = str(payment.request_key)
        request_started_at = payment.request_started_at

    # Phase 2: Contact the payment gateway OUTSIDE database transactions.
    try:
        result = gateway.request(
            payment,
            request_key=request_key,
        )
    except Exception:
        result = PaymentResult(
            success=False,
            message="نتیجه درخواست به درگاه مشخص نیست.",
            raw_response={"step": "request", "error": "gateway_exception"},
            outcome_unknown=True,
        )

    # A successful response without both values is not safe to use.
    if result.success and not (result.authority and result.redirect_url):
        result = PaymentResult(
            success=False,
            message="پاسخ درگاه ناقص است و نتیجه درخواست مشخص نیست.",
            raw_response={
                **result.raw_response,
                "step": "request",
                "error": "incomplete_gateway_response",
            },
            outcome_unknown=True,
        )

    # Phase 3: Persist the gateway result in another short transaction.
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        payment = Payment.objects.select_for_update().get(pk=payment_id)

        if (
            payment.status != "initiating"
            or payment.request_started_at != request_started_at
        ):
            redirect_url = (payment.gateway_response or {}).get("redirect_url")

            if payment.status == "pending" and payment.authority and redirect_url:
                return Response(
                    {
                        "success": True,
                        "payment_id": payment.id,
                        "redirect_url": redirect_url,
                    }
                )

            return Response(
                {
                    "success": False,
                    "error": "payment_request_state_changed",
                    "payment_id": payment.id,
                },
                status=409,
            )
        now = timezone.now()
        reservations_valid = False

        if order.status == "pending":
            reservations_valid, reservations, variants_by_id = (
                _lock_and_validate_reservations(order, now)
            )

            if not reservations_valid:
                cancel_locked_order(
                    order,
                    reservations,
                    now,
                    note=(
                        "لغو خودکار به علت پایان مهلت یا نامعتبر بودن "
                        "رزرو موجودی هنگام پاسخ درگاه."
                    ),
                )

        payment.gateway_response = {
            **(result.raw_response or {}),
            "step": "request",
        }

        if result.authority:
            payment.authority = result.authority
            payment.gateway_response["authority"] = result.authority

        if result.redirect_url:
            payment.gateway_response["redirect_url"] = result.redirect_url

        if result.success and order.status == "pending" and reservations_valid:
            payment.status = "pending"
            payment.save(
                update_fields=[
                    "status",
                    "authority",
                    "gateway_response",
                ]
            )

            response_data = {
                "success": True,
                "payment_id": payment.id,
                "redirect_url": result.redirect_url,
            }
            response_status = 200

        elif result.outcome_unknown or result.success:
            payment.status = "unknown"
            payment.save(
                update_fields=[
                    "status",
                    "authority",
                    "gateway_response",
                ]
            )

            response_data = {
                "success": False,
                "error": (
                    "نتیجه درخواست پرداخت مشخص نیست. "
                    "لطفاً درخواست پرداخت جدیدی ارسال نکنید."
                ),
                "payment_id": payment.id,
            }
            response_status = 409

        else:
            payment.status = "failed"
            payment.save(
                update_fields=[
                    "status",
                    "authority",
                    "gateway_response",
                ]
            )

            response_data = {
                "success": False,
                "error": result.message or "خطا در شروع پرداخت.",
                "payment_id": payment.id,
            }
            response_status = 502

    return Response(response_data, status=response_status)


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

    # Phase 1: Validate and claim verification in a short transaction.
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(
                order_number=order_number,
                user=request.user,
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

        now = timezone.now()

        payment = (
            Payment.objects.select_for_update()
            .filter(
                order=order,
                status="pending",
                authority=authority,
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if not payment:
            verification_in_progress = Payment.objects.filter(
                order=order,
                status="verifying",
                authority=authority,
            ).exists()

            if verification_in_progress:
                return Response(
                    {
                        "success": False,
                        "message": "تأیید این پرداخت در حال انجام است.",
                    },
                    status=409,
                )

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

        payment.status = "verifying"
        payment.verification_started_at = now
        payment.save(
            update_fields=[
                "status",
                "verification_started_at",
            ]
        )

        payment_id = payment.id
        order_id = order.id
        verification_started_at = payment.verification_started_at

    # Phase 2: Contact the gateway OUTSIDE database transactions.
    try:
        gateway = get_gateway()
        result = gateway.verify(
            payment,
            params={
                "status": status,
                "authority": authority,
            },
        )
    except Exception:
        result = PaymentResult(
            success=False,
            message="نتیجه تأیید پرداخت مشخص نیست.",
            raw_response={
                "step": "verify",
                "error": "gateway_exception",
            },
            outcome_unknown=True,
        )

    # Phase 3: Re-lock records and persist the verification result.
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        now = timezone.now()

        valid = False
        reservations = []
        variants_by_id = {}

        if order.status == "pending":
            valid, reservations, variants_by_id = _lock_and_validate_reservations(
                order, now
            )

        payment = Payment.objects.select_for_update().get(pk=payment_id)

        if (
            payment.status != "verifying"
            or payment.verification_started_at != verification_started_at
        ):
            if order.status == "paid":
                return Response({"success": True, "already_paid": True})

            return Response(
                {
                    "success": False,
                    "message": "وضعیت تأیید پرداخت تغییر کرده است.",
                },
                status=409,
            )

        if result.outcome_unknown:
            payment.status = "unknown"
            payment.gateway_response = {
                **(result.raw_response or {}),
                "step": "verify",
                "outcome_unknown": True,
            }
            payment.save(
                update_fields=[
                    "status",
                    "gateway_response",
                ]
            )

            return Response(
                {
                    "success": False,
                    "message": (
                        "نتیجه پرداخت مشخص نیست. "
                        "لطفاً درخواست پرداخت جدیدی ارسال نکنید."
                    ),
                },
                status=409,
            )
        if result.success and not result.ref_id:
            payment.status = "unknown"
            payment.gateway_response = {
                **(result.raw_response or {}),
                "step": "verify",
                "error": "missing_ref_id",
                "outcome_unknown": True,
            }
            payment.save(
                update_fields=[
                    "status",
                    "gateway_response",
                ]
            )

            return Response(
                {
                    "success": False,
                    "message": (
                        "درگاه پرداخت موفقیت را اعلام کرده، "
                        "اما شناسه پیگیری دریافت نشده است. "
                        "وضعیت پرداخت نیازمند بررسی است."
                    ),
                },
                status=409,
            )
        if not result.success:
            payment.status = "cancelled" if status == "cancelled" else "failed"
            payment.gateway_response = result.raw_response or {}
            payment.save(
                update_fields=[
                    "status",
                    "gateway_response",
                ]
            )

            return Response(
                {
                    "success": False,
                    "message": result.message or "پرداخت ناموفق بود.",
                },
                status=400,
            )

        # The gateway reports success, but the order or reservation
        # may no longer be eligible for payment completion.
        if order.status != "pending" or not valid:
            if order.status == "pending":
                cancel_locked_order(
                    order,
                    reservations,
                    now,
                    note=(
                        "لغو خودکار به علت پایان مهلت یا نامعتبر بودن "
                        "رزرو موجودی هنگام تأیید پرداخت."
                    ),
                )

            payment.status = "unknown"
            payment.gateway_response = {
                **(result.raw_response or {}),
                "step": "verify",
                "reason": "order_or_reservation_no_longer_valid",
            }
            payment.save(
                update_fields=[
                    "status",
                    "gateway_response",
                ]
            )

            return Response(
                {
                    "success": False,
                    "message": (
                        "درگاه پرداخت را موفق اعلام کرده، اما سفارش "
                        "قابل تکمیل نیست. وضعیت پرداخت نیازمند بررسی است."
                    ),
                },
                status=409,
            )

        completed = _complete_successful_payment(
            order=order,
            payment=payment,
            reservations=reservations,
            now=now,
            result=result,
        )

        if not completed:
            return Response(
                {
                    "success": False,
                    "message": (
                        "پرداخت توسط درگاه موفق اعلام شده، اما ثبت فروش "
                        "در انبار انجام نشد. وضعیت پرداخت نیازمند بررسی است."
                    ),
                },
                status=409,
            )

        return Response(
            {
                "success": True,
                "ref_id": payment.ref_id,
                "order_number": order.order_number,
            }
        )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def recover_payment(request):
    order_number = request.data.get("order_number")

    if not order_number:
        return Response(
            {"error": "شماره سفارش الزامی است."},
            status=400,
        )

    # Phase 1: Claim the recovery operation.
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(
                order_number=order_number,
                user=request.user,
            )
        except Order.DoesNotExist:
            return Response(
                {"error": "سفارش یافت نشد."},
                status=404,
            )

        payment = (
            Payment.objects.select_for_update()
            .filter(order=order)
            .order_by("-created_at", "-id")
            .first()
        )

        if not payment:
            return Response(
                {"error": "پرداختی برای این سفارش پیدا نشد."},
                status=404,
            )

        if payment.status == "pending":
            return Response(
                {
                    "success": False,
                    "error": (
                        "این پرداخت در انتظار تأیید است؛ "
                        "از مسیر تأیید پرداخت استفاده کنید."
                    ),
                    "payment_id": payment.id,
                },
                status=409,
            )

        if payment.status not in ["initiating", "unknown"]:
            return Response(
                {
                    "success": False,
                    "error": "وضعیت فعلی پرداخت قابل بازیابی نیست.",
                    "payment_id": payment.id,
                    "status": payment.status,
                },
                status=409,
            )

        now = timezone.now()

        can_claim, claim_error = _can_claim_recovery(payment, now)

        if not can_claim:
            return Response(
                {
                    "success": False,
                    "error": claim_error,
                    "payment_id": payment.id,
                },
                status=409,
            )

        recovery_operation, _ = _get_recovery_operation(payment)

        payment.inquiry_started_at = now
        payment.save(update_fields=["inquiry_started_at"])

        payment_id = payment.id
        order_id = order.id
        inquiry_started_at = payment.inquiry_started_at

    # Phase 2: Contact the gateway outside the transaction.
    try:
        gateway = get_gateway()

        if recovery_operation == "request":
            result = gateway.inquire(
                payment,
                payment.request_key,
            )
        elif recovery_operation == "verify":
            result = gateway.inquire_transaction(payment)
        else:
            raise ValueError("Unsupported recovery operation")

    except Exception:
        result = PaymentResult(
            success=False,
            outcome_unknown=True,
            message="Gateway recovery inquiry failed",
            raw_response={
                "step": recovery_operation,
                "error": "gateway_exception",
            },
        )

    # Phase 3: Re-lock records and persist the recovery result.
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=order_id)
        payment = Payment.objects.select_for_update().get(
            pk=payment_id,
            order_id=order.id,
        )

        if (
            payment.status not in ["initiating", "unknown"]
            or payment.inquiry_started_at != inquiry_started_at
        ):
            if order.status == "paid":
                return Response(
                    {
                        "success": True,
                        "already_paid": True,
                    }
                )

            return Response(
                {
                    "success": False,
                    "error": "recovery_state_changed",
                    "payment_id": payment.id,
                },
                status=409,
            )
        now = timezone.now()

        valid = False
        reservations = []
        variants_by_id = {}

        # Validate reservations before restoring a payment session or
        # completing a payment after a successful gateway inquiry.
        if (
            recovery_operation in ["request", "verify"]
            and result.success
            and order.status == "pending"
        ):
            valid, reservations, variants_by_id = _lock_and_validate_reservations(
                order, now
            )

        # Recovery of the original payment request:
        # A successful inquiry restores the payment session only.

        if recovery_operation == "request":
            if result.success and valid and result.authority and result.redirect_url:
                payment.status = "pending"
                payment.authority = result.authority
                payment.gateway_response = {
                    **(result.raw_response or {}),
                    "step": "request",
                    "authority": result.authority,
                    "redirect_url": result.redirect_url,
                    "request_key": str(payment.request_key),
                }
                payment.save(
                    update_fields=[
                        "status",
                        "authority",
                        "gateway_response",
                    ]
                )

                return Response(
                    {
                        "success": True,
                        "recovered": True,
                        "payment_id": payment.id,
                        "redirect_url": result.redirect_url,
                    }
                )

            # A request inquiry cannot by itself prove payment failure.
            payment.status = "unknown"
            payment.gateway_response = {
                **(result.raw_response or {}),
                "step": "request",
                "outcome_unknown": True,
            }
            payment.save(
                update_fields=[
                    "status",
                    "gateway_response",
                ]
            )

            return Response(
                {
                    "success": False,
                    "error": "payment_request_still_unknown",
                    "payment_id": payment.id,
                },
                status=409,
            )

        # Recovery of the original verification:
        if result.outcome_unknown:
            payment.status = "unknown"
            payment.gateway_response = {
                **(result.raw_response or {}),
                "step": "verify",
                "outcome_unknown": True,
            }
            payment.save(
                update_fields=[
                    "status",
                    "gateway_response",
                ]
            )

            return Response(
                {
                    "success": False,
                    "error": "payment_status_still_unknown",
                    "payment_id": payment.id,
                },
                status=409,
            )

        if result.success and not result.ref_id:
            payment.status = "unknown"
            payment.gateway_response = {
                **(result.raw_response or {}),
                "step": "verify",
                "error": "missing_ref_id",
                "outcome_unknown": True,
            }
            payment.save(
                update_fields=[
                    "status",
                    "gateway_response",
                ]
            )

            return Response(
                {
                    "success": False,
                    "error": "missing_ref_id",
                    "payment_id": payment.id,
                },
                status=409,
            )

        if not result.success:
            payment.status = "failed"
            payment.gateway_response = {
                **(result.raw_response or {}),
                "step": "verify",
            }
            payment.save(
                update_fields=[
                    "status",
                    "gateway_response",
                ]
            )

            return Response(
                {
                    "success": False,
                    "message": result.message or "پرداخت ناموفق بود.",
                    "payment_id": payment.id,
                },
                status=400,
            )

        if recovery_operation == "verify" and payment.amount != order.total_amount:
            payment.status = "unknown"
            payment.gateway_response = {
                **(result.raw_response or {}),
                "step": "verify",
                "reason": "payment_amount_mismatch",
                "outcome_unknown": True,
            }
            payment.save(
                update_fields=[
                    "status",
                    "gateway_response",
                ]
            )

            return Response(
                {
                    "success": False,
                    "error": "payment_amount_mismatch",
                    "payment_id": payment.id,
                },
                status=409,
            )

        # Gateway confirms success, but the order or reservations
        # may no longer be eligible for payment completion.
        if order.status != "pending" or not valid:
            if order.status == "pending":
                cancel_locked_order(
                    order,
                    reservations,
                    now,
                    note=(
                        "لغو خودکار به علت پایان مهلت یا نامعتبر بودن "
                        "رزرو موجودی هنگام بازیابی پرداخت."
                    ),
                )

            payment.status = "unknown"
            payment.gateway_response = {
                **(result.raw_response or {}),
                "step": "verify",
                "reason": "order_or_reservation_no_longer_valid",
            }
            payment.save(
                update_fields=[
                    "status",
                    "gateway_response",
                ]
            )

            return Response(
                {
                    "success": False,
                    "error": "order_or_reservation_no_longer_valid",
                    "payment_id": payment.id,
                },
                status=409,
            )

        completed = _complete_successful_payment(
            order=order,
            payment=payment,
            reservations=reservations,
            now=now,
            result=result,
        )

        if not completed:
            return Response(
                {
                    "success": False,
                    "error": "inventory_sale_failed",
                    "payment_id": payment.id,
                },
                status=409,
            )

        return Response(
            {
                "success": True,
                "ref_id": payment.ref_id,
                "order_number": order.order_number,
            }
        )


@require_http_methods(["GET", "POST"])
def mock_payment_page(request, payment_id):
    """Mock bank page. Acts as the payment gateway UI."""

    if (
        not settings.DEBUG
        or getattr(settings, "ACTIVE_PAYMENT_GATEWAY", "").strip().lower() != "mock"
    ):
        raise Http404

    if request.method == "POST":
        submitted_status = request.POST.get("status")

        if submitted_status not in ["success", "cancelled"]:
            return HttpResponseBadRequest("Invalid payment status")

        status = "success" if submitted_status == "success" else "failed"

        try:
            payment_order_id = Payment.objects.values_list(
                "order_id",
                flat=True,
            ).get(pk=payment_id)
        except Payment.DoesNotExist:
            raise Http404

        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(
                    pk=payment_order_id,
                )
            except Order.DoesNotExist:
                raise Http404

            now = timezone.now()
            valid, reservations, variants_by_id = _lock_and_validate_reservations(
                order, now
            )

            try:
                payment = Payment.objects.select_for_update().get(
                    pk=payment_id,
                    order_id=order.id,
                )
            except Payment.DoesNotExist:
                raise Http404

            if payment.status != "pending" or order.status != "pending":
                return render(
                    request,
                    "payments/mock_already_processed.html",
                    {"payment": payment, "order": order},
                )

            try:
                mock_transaction = (
                    MockGatewayTransaction.objects.select_for_update().get(
                        payment=payment,
                        authority=payment.authority,
                    )
                )
            except MockGatewayTransaction.DoesNotExist:
                raise Http404

            if mock_transaction.status != "pending":
                return render(
                    request,
                    "payments/mock_already_processed.html",
                    {"payment": payment, "order": order},
                )

            if not valid:
                mock_transaction.status = "failed"
                mock_transaction.raw_response = {
                    "step": "mock_payment",
                    "reason": "reservation_expired_or_invalid",
                    "status": "failed",
                }
                mock_transaction.save(
                    update_fields=[
                        "status",
                        "raw_response",
                        "updated_at",
                    ]
                )

                payment.status = "failed"
                payment.gateway_response = {
                    "step": "mock_payment",
                    "reason": "reservation_expired_or_invalid",
                }
                payment.save(
                    update_fields=[
                        "status",
                        "gateway_response",
                    ]
                )

                cancel_locked_order(
                    order,
                    reservations,
                    now,
                    note="لغو خودکار به علت پایان مهلت یا نامعتبر بودن رزرو موجودی در صفحه پرداخت آزمایشی.",
                )

                return render(
                    request,
                    "payments/mock_already_processed.html",
                    {"payment": payment, "order": order},
                )

            ref_id = ""

            if status == "success":
                import uuid

                ref_id = "MOCK-REF-" + uuid.uuid4().hex[:12].upper()

            mock_transaction.status = status
            mock_transaction.ref_id = ref_id
            mock_transaction.raw_response = {
                "step": "mock_payment",
                "submitted_status": submitted_status,
                "status": status,
                "authority": mock_transaction.authority,
                "ref_id": ref_id,
            }
            mock_transaction.save(
                update_fields=[
                    "status",
                    "ref_id",
                    "raw_response",
                    "updated_at",
                ]
            )

        frontend_url = settings.FRONTEND_URL

        return redirect(
            f"{frontend_url}/checkout/callback"
            f"?order={order.order_number}"
            f"&status={submitted_status}"
            f"&authority={payment.authority}"
        )

    payment_order_id = (
        Payment.objects.filter(pk=payment_id).values_list("order_id", flat=True).first()
    )
    if payment_order_id is None:
        raise Http404

    with transaction.atomic():
        order = get_object_or_404(
            Order.objects.select_for_update(),
            pk=payment_order_id,
        )

        now = timezone.now()
        valid, reservations, variants_by_id = _lock_and_validate_reservations(
            order, now
        )

        payment = get_object_or_404(
            Payment.objects.select_for_update(),
            pk=payment_id,
            order_id=order.id,
        )

        mock_transaction = get_object_or_404(
            MockGatewayTransaction.objects.select_for_update(),
            payment=payment,
            authority=payment.authority,
        )

        if (
            payment.status != "pending"
            or order.status != "pending"
            or mock_transaction.status != "pending"
            or not valid
        ):
            return render(
                request,
                "payments/mock_already_processed.html",
                {"payment": payment, "order": order},
            )

    return render(
        request,
        "payments/mock_payment.html",
        {"payment": payment, "order": order},
    )
