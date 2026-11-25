from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import F, Q, Sum
from django.utils import timezone

from catalog.models import ProductVariant
from orders.models import StockReservation

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


def get_variants_batch_inventory(variant_ids, today=None, now=None):
    """
    Return physical and effective reserved quantities per batch.

    Explicit allocations stay attached to their batches. Active reservations
    that have not yet been fully allocated are virtually protected in FEFO
    order, matching allocate_stock_reservation and outbound document approval.
    No allocation records are created or changed by this reporting helper.
    """
    today = today or timezone.localdate()
    now = now or timezone.now()
    variant_ids = list(dict.fromkeys(variant_ids))

    if not variant_ids:
        return {}

    batches = list(
        InventoryBatch.objects.filter(
            variant_id__in=variant_ids,
        )
        .order_by(
            "variant_id",
            F("expiration_date").asc(nulls_last=True),
            "id",
        )
        .values("id", "variant_id", "status", "expiration_date")
    )
    if not batches:
        return {}

    physical_by_batch = {
        row["batch_id"]: row["total"] or 0
        for row in InventoryMovement.objects.filter(
            batch__variant_id__in=variant_ids,
        )
        .values("batch_id")
        .annotate(total=Sum("quantity_delta"))
    }

    active_allocation_rows = ReservationAllocation.objects.filter(
        batch__variant_id__in=variant_ids,
        reservation__status="active",
        reservation__expires_at__gt=now,
        reservation__order__reservation_expires_at__gt=now,
        reservation__order__status="pending",
    ).values("batch_id", "reservation__variant_id").annotate(
        total=Sum("quantity"),
    )

    reserved_by_batch = {}
    allocated_by_variant = {}
    for row in active_allocation_rows:
        batch_id = row["batch_id"]
        reservation_variant_id = row["reservation__variant_id"]
        quantity = row["total"] or 0
        reserved_by_batch[batch_id] = (
            reserved_by_batch.get(batch_id, 0) + quantity
        )
        allocated_by_variant[reservation_variant_id] = (
            allocated_by_variant.get(reservation_variant_id, 0) + quantity
        )

    reserved_by_variant = {
        row["variant_id"]: row["total"] or 0
        for row in StockReservation.objects.filter(
            variant_id__in=variant_ids,
            status="active",
            expires_at__gt=now,
            order__status="pending",
            order__reservation_expires_at__gt=now,
        )
        .values("variant_id")
        .annotate(total=Sum("quantity"))
    }

    unallocated_by_variant = {
        variant_id: max(
            reserved_by_variant.get(variant_id, 0)
            - allocated_by_variant.get(variant_id, 0),
            0,
        )
        for variant_id in variant_ids
    }

    result = {
        batch["id"]: {
            "physical": physical_by_batch.get(batch["id"], 0),
            "reserved": reserved_by_batch.get(batch["id"], 0),
        }
        for batch in batches
    }

    for batch in batches:
        if batch["status"] != "available" or (
            batch["expiration_date"] is not None
            and batch["expiration_date"] < today
        ):
            continue

        variant_id = batch["variant_id"]
        unallocated = unallocated_by_variant.get(variant_id, 0)
        if not unallocated:
            continue

        batch_id = batch["id"]
        physical = result[batch_id]["physical"]
        explicitly_reserved = result[batch_id]["reserved"]
        unreserved_physical = max(physical - explicitly_reserved, 0)
        virtually_reserved = min(unreserved_physical, unallocated)

        result[batch_id]["reserved"] += virtually_reserved
        unallocated_by_variant[variant_id] -= virtually_reserved

    return result


def get_batch_available_quantity(batch, today=None, now=None):
    today = today or timezone.localdate()
    now = now or timezone.now()

    if batch.status != "available":
        return 0

    if batch.expiration_date and batch.expiration_date < today:
        return 0

    quantities = get_variants_batch_inventory(
        [batch.variant_id],
        today=today,
        now=now,
    ).get(batch.id, {"physical": 0, "reserved": 0})

    return max(quantities["physical"] - quantities["reserved"], 0)


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


from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from orders.models import StockReservation


@transaction.atomic
def allocate_stock_reservation(reservation, now=None):
    now = now or timezone.now()
    today = timezone.localdate()
    ProductVariant.objects.select_for_update().get(
        pk=reservation.variant_id,
    )
    if (
        reservation.status != "active"
        or reservation.expires_at <= now
        or reservation.order.status != "pending"
        or reservation.order.reservation_expires_at <= now
    ):
        raise ValidationError(
            "Cannot allocate stock for an inactive or expired reservation."
        )

    if ReservationAllocation.objects.filter(
        reservation=reservation,
    ).exists():
        raise ValidationError("This reservation has already been allocated.")

    batches = list(
        InventoryBatch.objects.select_for_update()
        .filter(
            variant_id=reservation.variant_id,
            status="available",
        )
        .filter(Q(expiration_date__isnull=True) | Q(expiration_date__gte=today))
        .order_by(
            F("expiration_date").asc(nulls_last=True),
            "id",
        )
    )

    active_reservations = StockReservation.objects.filter(
        variant_id=reservation.variant_id,
        status="active",
        expires_at__gt=now,
        order__status="pending",
        order__reservation_expires_at__gt=now,
    )

    existing_reservations = active_reservations.exclude(
        pk=reservation.pk,
    )

    existing_reserved = (
        existing_reservations.aggregate(
            total=Sum("quantity"),
        )["total"]
        or 0
    )

    existing_allocated = (
        ReservationAllocation.objects.filter(
            reservation__in=existing_reservations,
        ).aggregate(total=Sum("quantity"),)["total"]
        or 0
    )

    unallocated_reserved = max(
        existing_reserved - existing_allocated,
        0,
    )

    remaining = reservation.quantity

    for batch in batches:
        physical = get_batch_physical_quantity(batch)

        allocated = get_batch_reserved_quantity(
            batch,
            now=now,
        )

        available = max(physical - allocated, 0)

        protected = min(available, unallocated_reserved)
        available -= protected
        unallocated_reserved -= protected

        quantity = min(available, remaining)

        if quantity <= 0:
            continue

        ReservationAllocation.objects.create(
            reservation=reservation,
            batch=batch,
            quantity=quantity,
        )

        remaining -= quantity

        if remaining == 0:
            break

    if remaining:
        raise ValidationError("Insufficient available batch stock for reservation.")
