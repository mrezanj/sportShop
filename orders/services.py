from django.db import transaction
from django.utils import timezone

from .models import Order, OrderStatusHistory

# وضعیت‌های مجاز بعدی برای هر وضعیت فعلی
ALLOWED_ORDER_TRANSITIONS = {
    "pending": {"paid", "cancelled"},
    "paid": {"processing"},
    "processing": {"shipped"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
}


class InvalidOrderStatusTransition(Exception):
    pass


@transaction.atomic
def transition_order_status(
    order,
    new_status,
    changed_by=None,
    note="",
):
    """
    Change an order status and record its history atomically.

    The caller is responsible for locking the order when concurrent
    status changes are possible.
    """
    valid_statuses = dict(Order.STATUS_CHOICES)

    if new_status not in valid_statuses:
        raise InvalidOrderStatusTransition(f"وضعیت سفارش نامعتبر است: {new_status}")

    old_status = order.status

    if old_status == new_status:
        return False

    allowed = ALLOWED_ORDER_TRANSITIONS.get(old_status, set())

    if new_status not in allowed:
        raise InvalidOrderStatusTransition(
            f"تغییر وضعیت از {old_status} به {new_status} مجاز نیست."
        )

    order.status = new_status
    order.save(update_fields=["status", "updated_at"])

    OrderStatusHistory.objects.create(
        order=order,
        old_status=old_status,
        new_status=new_status,
        changed_by=changed_by,
        note=note,
    )

    return True


def release_active_reservations(reservations, now=None):
    now = now or timezone.now()

    for reservation in reservations:
        if reservation.status != "active":
            continue

        reservation.status = "expired" if reservation.expires_at <= now else "released"
        reservation.released_at = now
        reservation.save(update_fields=["status", "released_at"])


@transaction.atomic
def cancel_locked_order(
    order,
    reservations,
    now=None,
    changed_by=None,
    note="",
):
    now = now or timezone.now()

    release_active_reservations(reservations, now)

    return transition_order_status(
        order=order,
        new_status="cancelled",
        changed_by=changed_by,
        note=note,
    )
