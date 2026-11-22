from django.db import models
from django.db.models import Q, Sum
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
            batch.expiration_date is None or batch.expiration_date >= today
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
        ).aggregate(total=Sum("quantity"),)["total"]
        or 0
    )

    available = max(sellable_physical - reserved, 0)

    return {
        "physical": physical,
        "reserved": reserved,
        "available": available,
    }


def get_variants_inventory(variants, today=None, now=None):
    today = today or timezone.localdate()
    now = now or timezone.now()

    variant_ids = [variant.id for variant in variants]

    if not variant_ids:
        return {}

    physical_rows = (
        InventoryMovement.objects.filter(
            batch__variant_id__in=variant_ids,
        )
        .values("batch__variant_id")
        .annotate(total=Sum("quantity_delta"))
    )

    sellable_rows = (
        InventoryMovement.objects.filter(
            batch__variant_id__in=variant_ids,
            batch__status="available",
        )
        .filter(
            models.Q(batch__expiration_date__isnull=True)
            | models.Q(batch__expiration_date__gte=today)
        )
        .values("batch__variant_id")
        .annotate(total=Sum("quantity_delta"))
    )

    from orders.models import StockReservation

    reserved_rows = (
        StockReservation.objects.filter(
            variant_id__in=variant_ids,
            status="active",
            expires_at__gt=now,
            order__status="pending",
            order__reservation_expires_at__gt=now,
        )
        .values("variant_id")
        .annotate(total=Sum("quantity"))
    )

    physical = {row["batch__variant_id"]: row["total"] or 0 for row in physical_rows}
    sellable_physical = {
        row["batch__variant_id"]: row["total"] or 0 for row in sellable_rows
    }
    reserved = {row["variant_id"]: row["total"] or 0 for row in reserved_rows}

    return {
        variant_id: {
            "physical": physical.get(variant_id, 0),
            "reserved": reserved.get(variant_id, 0),
            "available": max(
                sellable_physical.get(variant_id, 0) - reserved.get(variant_id, 0),
                0,
            ),
        }
        for variant_id in variant_ids
    }
