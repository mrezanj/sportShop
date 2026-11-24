from django.db import transaction
from django.utils import timezone

from .models import Order, ReturnRequest, ReturnRequestItem, OrderItem, ReturnRequestHistory


class ReturnRequestError(Exception):
    pass


@transaction.atomic
def create_return_request(*, order_number, user, reason, items):
    order = Order.objects.select_for_update().get(order_number=order_number, user=user)
    if order.status not in {"paid", "processing", "shipped", "delivered"}:
        raise ReturnRequestError("برای این وضعیت سفارش امکان درخواست مرجوعی وجود ندارد.")
    if ReturnRequest.objects.filter(
        order=order, status__in=["requested", "approved", "received"]
    ).exists():
        raise ReturnRequestError("برای این سفارش درخواست مرجوعی فعال وجود دارد.")
    if not isinstance(reason, str) or not reason.strip() or not isinstance(items, list) or not items:
        raise ReturnRequestError("علت و اقلام مرجوعی الزامی هستند.")
    request = ReturnRequest.objects.create(order=order, user=user, reason=reason.strip())
    ReturnRequestHistory.objects.create(
        return_request=request, old_status="", new_status="requested",
        changed_by=user, note="ثبت درخواست توسط مشتری.",
    )
    seen = set()
    for entry in items:
        try:
            item_id, quantity = int(entry["order_item_id"]), int(entry["quantity"])
        except (KeyError, TypeError, ValueError):
            raise ReturnRequestError("قلم یا تعداد مرجوعی نامعتبر است.")
        if item_id in seen or quantity <= 0:
            raise ReturnRequestError("اقلام تکراری یا تعداد نامعتبر است.")
        seen.add(item_id)
        item = OrderItem.objects.select_for_update().filter(pk=item_id, order=order).first()
        if not item or quantity > item.quantity:
            raise ReturnRequestError("قلم سفارش یافت نشد یا تعداد درخواستی بیش از خرید است.")
        already_requested = ReturnRequestItem.objects.filter(
            order_item=item,
            return_request__status__in=["requested", "approved", "received"],
        ).values_list("quantity", flat=True)
        if quantity + sum(already_requested) > item.quantity:
            raise ReturnRequestError("تعداد مرجوعی از تعداد خریداری‌شده بیشتر است.")
        ReturnRequestItem.objects.create(
            return_request=request, order_item=item, quantity=quantity
        )
    return request


@transaction.atomic
def review_return_request(*, request_id, actor, decision, note=""):
    request = ReturnRequest.objects.select_for_update().get(pk=request_id)
    if request.status != "requested":
        raise ReturnRequestError("این درخواست قبلاً بررسی شده است.")
    if decision not in {"approved", "rejected"}:
        raise ReturnRequestError("تصمیم بررسی نامعتبر است.")
    request.status = decision
    request.reviewed_by = actor
    request.staff_note = note
    old_status = request.status
    request.save(update_fields=["status", "reviewed_by", "staff_note", "updated_at"])
    ReturnRequestHistory.objects.create(
        return_request=request, old_status=old_status, new_status=decision,
        changed_by=actor, note=note,
    )
    return request


@transaction.atomic
def mark_return_received(*, request_id, actor, note=""):
    request = ReturnRequest.objects.select_for_update().get(pk=request_id)
    if request.status != "approved":
        raise ReturnRequestError("فقط درخواست تأییدشده قابل ثبت به‌عنوان کالای دریافت‌شده است.")
    request.status = "received"
    request.reviewed_by = actor
    request.staff_note = note
    old_status = request.status
    request.save(update_fields=["status", "reviewed_by", "staff_note", "updated_at"])
    ReturnRequestHistory.objects.create(
        return_request=request, old_status=old_status, new_status="received",
        changed_by=actor, note=note,
    )
    return request
