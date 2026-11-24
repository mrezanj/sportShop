from django.db import transaction
from django.utils import timezone

from .models import Order, OrderDiscrepancy, OrderStatusHistory


class DiscrepancyError(Exception):
    pass


@transaction.atomic
def open_order_discrepancy(*, order_id, reason, actor):
    order = Order.objects.select_for_update().get(pk=order_id)
    if not isinstance(reason, str) or not reason.strip():
        raise DiscrepancyError("شرح مغایرت الزامی است.")
    if order.status in ("pending", "cancelled", "discrepancy"):
        raise DiscrepancyError("برای وضعیت فعلی سفارش امکان ثبت مغایرت وجود ندارد.")
    if OrderDiscrepancy.objects.filter(order=order, status="open").exists():
        raise DiscrepancyError("برای این سفارش پرونده مغایرت باز وجود دارد.")
    case = OrderDiscrepancy.objects.create(
        order=order, reason=reason, opened_by=actor,
        previous_order_status=order.status,
    )
    old_status = order.status
    order.status = "discrepancy"
    order.save(update_fields=["status", "updated_at"])
    OrderStatusHistory.objects.create(
        order=order, old_status=old_status, new_status="discrepancy",
        changed_by=actor, note=f"توقف سفارش به علت مغایرت: {reason}",
    )
    return case


@transaction.atomic
def resolve_order_discrepancy(*, case_id, resolution, actor):
    order_id = OrderDiscrepancy.objects.values_list("order_id", flat=True).get(pk=case_id)
    order = Order.objects.select_for_update().get(pk=order_id)
    case = OrderDiscrepancy.objects.select_for_update().get(pk=case_id, order_id=order_id)
    if not isinstance(resolution, str) or not resolution.strip():
        raise DiscrepancyError("شرح نتیجه رسیدگی الزامی است.")
    if case.status != "open" or order.status != "discrepancy":
        raise DiscrepancyError("پرونده مغایرت باز و قابل رسیدگی نیست.")
    restored = case.previous_order_status
    if restored not in {"paid", "processing", "shipped", "delivered"}:
        raise DiscrepancyError("وضعیت قبلی سفارش معتبر نیست.")
    case.status = "resolved"
    case.resolution = resolution
    case.resolved_by = actor
    case.resolved_at = timezone.now()
    case.save(update_fields=["status", "resolution", "resolved_by", "resolved_at"])
    order.status = restored
    order.save(update_fields=["status", "updated_at"])
    OrderStatusHistory.objects.create(
        order=order, old_status="discrepancy", new_status=restored,
        changed_by=actor, note=f"رفع مغایرت: {resolution}",
    )
    return case
