from django.db.models import Sum
from django.utils import timezone

from .models import (
    InventoryBatch,
    InventoryMovement,
    ReservationAllocation,
)


def get_batch_physical_quantity(batch):
    result = InventoryMovement.objects.filter(
        batch=batch,
    ).aggregate(
        total=Sum("quantity_delta"),
    )
    return result["total"] or 0


def get_batch_reserved_quantity(batch, now=None):
    now = now or timezone.now()

    result = ReservationAllocation.objects.filter(
        batch=batch,
        reservation__status="active",
        reservation__expires_at__gt=now,
        reservation__order__reservation_expires_at__gt=now,
        reservation__order__status="pending",
    ).aggregate(
        total=Sum("quantity"),
    )
    return result["total"] or 0


def get_batch_available_quantity(batch, today=None, now=None):
    today = today or timezone.localdate()
    now = now or timezone.now()

    if batch.status != "available":
        return 0

    if batch.expiration_date and batch.expiration_date < today:
        return 0

    physical = get_batch_physical_quantity(batch)
    reserved = get_batch_reserved_quantity(batch, now=now)

    return max(physical - reserved, 0)


def get_variant_inventory(variant, today=None, now=None):
    today = today or timezone.localdate()
    now = now or timezone.now()

    batches = InventoryBatch.objects.filter(
        variant=variant,
    )

    physical = 0
    sellable_physical = 0

    for batch in batches:
        batch_physical = get_batch_physical_quantity(batch)
        physical += batch_physical

        if batch.status == "available" and (
            batch.expiration_date is None
            or batch.expiration_date >= today
        ):
            sellable_physical += batch_physical

    from orders.models import StockReservation

    reserved = (
        StockReservation.objects.filter(
            variant=variant,
            status="active",
            expires_at__gt=now,
            order__status="pending",
            order__reservation_expires_at__gt=now,
        ).aggregate(
            total=Sum("quantity"),
        )["total"]
        or 0
    )

    available = max(sellable_physical - reserved, 0)

    return {
        "physical": physical,
        "reserved": reserved,
        "available": available,
    }