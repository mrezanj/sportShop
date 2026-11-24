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




def release_order_discount_redemptions(order):
    from catalog.models import DiscountCampaign, DiscountRedemption

    campaign_ids = list(
        DiscountRedemption.objects.filter(
            order=order,
            status="reserved",
        ).values_list("campaign_id", flat=True)
    )
    locked_campaigns = (
        DiscountCampaign.objects.select_for_update()
        .filter(pk__in=campaign_ids)
        .order_by("-priority", "id")
    )
    campaigns = {
        campaign.pk: campaign
        for campaign in locked_campaigns
    }
    redemptions = list(
        DiscountRedemption.objects.select_for_update()
        .filter(order=order, status="reserved")
        .order_by("campaign_id")
    )
    for redemption in redemptions:
        campaign = campaigns[redemption.campaign_id]
        campaign.usage_count = max(campaign.usage_count - 1, 0)
        campaign.save(update_fields=["usage_count", "updated_at"])
        redemption.status = "released"
        redemption.save(update_fields=["status"])


@transaction.atomic
def consume_order_discount_redemptions(order):
    from catalog.models import DiscountRedemption

    DiscountRedemption.objects.select_for_update().filter(
        order=order,
        status="reserved",
    ).update(status="consumed")


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
    release_order_discount_redemptions(order)

    return transition_order_status(
        order=order,
        new_status="cancelled",
        changed_by=changed_by,
        note=note,
    )
