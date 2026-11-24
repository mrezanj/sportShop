from decimal import Decimal, InvalidOperation
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from .models import Payment, Refund, RefundHistory
from orders.models import ReturnRequest


class RefundError(Exception):
    pass


@transaction.atomic
def create_refund(*, return_request_id, amount, actor, idempotency_key=None):
    request = ReturnRequest.objects.select_for_update().select_related("order").get(pk=return_request_id)
    try:
        amount = Decimal(str(amount))
        key = UUID(str(idempotency_key)) if idempotency_key else None
    except (InvalidOperation, TypeError, ValueError):
        raise RefundError("مبلغ یا کلید یکتای درخواست نامعتبر است.")
    if key is None:
        raise RefundError("کلید یکتای درخواست بازپرداخت الزامی است.")
    if not amount.is_finite() or amount <= 0:
        raise RefundError("مبلغ بازپرداخت باید بیشتر از صفر باشد.")
    if amount != amount.to_integral_value():
        raise RefundError("مبلغ بازپرداخت باید به تومان کامل وارد شود.")

    existing = Refund.objects.filter(idempotency_key=key).first()
    if existing:
        if existing.return_request_id != request.pk or existing.amount != amount:
            raise RefundError("کلید یکتای درخواست قبلاً برای اطلاعات دیگری استفاده شده است.")
        return existing

    if request.status != "received":
        raise RefundError("بازپرداخت فقط پس از دریافت و بررسی کالای مرجوعی مجاز است.")
    payments = list(
        Payment.objects.select_for_update().filter(
            order=request.order, status="success"
        ).order_by("id")
    )
    if not payments:
        raise RefundError("برای سفارش پرداخت موفقی ثبت نشده است.")
    payment = payments[0]

    # Locking the successful payment serializes concurrent refund reservations.
    existing = Refund.objects.filter(idempotency_key=key).first()
    if existing:
        if existing.return_request_id != request.pk or existing.amount != amount:
            raise RefundError("کلید یکتای درخواست قبلاً برای اطلاعات دیگری استفاده شده است.")
        return existing

    refunds = Refund.objects.select_for_update().filter(payment=payment)
    successful = sum(
        (row.amount for row in refunds.filter(status="succeeded")), Decimal("0")
    )
    reserved = sum(
        (
            row.amount
            for row in refunds.exclude(
                status__in=["failed", "rejected", "succeeded"]
            )
        ),
        Decimal("0"),
    )
    if successful + reserved + amount > payment.amount:
        raise RefundError("مجموع بازپرداخت‌ها نمی‌تواند از مبلغ پرداخت موفق بیشتر باشد.")
    refund = Refund.objects.create(
        return_request=request, payment=payment, amount=amount,
        requested_by=actor, idempotency_key=key,
    )
    RefundHistory.objects.create(
        refund=refund, old_status="", new_status="requested",
        changed_by=actor, note="ایجاد درخواست بازپرداخت.",
    )
    return refund

@transaction.atomic
def transition_refund(*, refund_id, actor, decision, provider_reference="", provider_response=None):
    refund = Refund.objects.select_for_update().select_related("payment").get(pk=refund_id)
    if not isinstance(provider_reference, str):
        provider_reference = ""
    response = provider_response if isinstance(provider_response, dict) else {}
    old_status = refund.status
    target_status = {
        "approve": "approved", "processing": "processing",
        "succeeded": "succeeded", "failed": "failed", "reject": "rejected",
    }.get(decision)
    if target_status and refund.status == target_status:
        if decision == "succeeded" and refund.provider_reference != provider_reference:
            raise RefundError("بازپرداخت قبلاً با شناسه پیگیری دیگری نهایی شده است.")
        return refund
    if decision == "approve" and refund.status == "requested":
        refund.status = "approved"
    elif decision == "processing" and refund.status == "approved":
        refund.status = "processing"
    elif decision in {"succeeded", "failed"} and refund.status in {"approved", "processing"}:
        if decision == "succeeded" and not provider_reference.strip():
            raise RefundError("برای ثبت بازپرداخت موفق، شناسه پیگیری ارائه‌دهنده الزامی است.")
        if decision == "succeeded" and not response:
            raise RefundError("پاسخ یا مستند نتیجه بازپرداخت ارائه‌دهنده الزامی است.")
        refund.status = decision
        refund.completed_at = timezone.now()
    elif decision == "reject" and refund.status == "requested":
        refund.status = "rejected"
    else:
        raise RefundError("تغییر وضعیت بازپرداخت مجاز نیست.")
    refund.processed_by = actor
    refund.provider_reference = provider_reference
    refund.provider_response = response
    refund.save(update_fields=[
        "status", "processed_by", "provider_reference", "provider_response",
        "completed_at", "updated_at",
    ])
    RefundHistory.objects.create(
        refund=refund, old_status=old_status, new_status=refund.status,
        changed_by=actor, provider_reference=provider_reference,
        provider_response=response, note=f"تغییر وضعیت بازپرداخت به {refund.status}.",
    )
    if refund.status == "succeeded":
        from orders.models import ReturnRequest, ReturnRequestHistory
        other_pending = Refund.objects.filter(
            return_request=refund.return_request
        ).exclude(status__in=["succeeded", "failed", "rejected"]).exists()
        if not other_pending:
            return_request = ReturnRequest.objects.select_for_update().get(
                pk=refund.return_request_id
            )
            if return_request.status == "received":
                return_request.status = "closed"
                return_request.save(update_fields=["status", "updated_at"])
                ReturnRequestHistory.objects.create(
                    return_request=return_request, old_status="received",
                    new_status="closed", changed_by=actor,
                    note="تکمیل فرآیند بازپرداخت.",
                )
    return refund
