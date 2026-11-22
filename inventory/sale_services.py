from collections import defaultdict

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from orders.models import Order, StockReservation

from .models import (
    InventoryBatch,
    InventoryDocument,
    InventoryDocumentItem,
    InventoryDocumentLog,
    InventoryMovement,
    ReservationAllocation,
)
from .services import get_batch_physical_quantity


@transaction.atomic
def record_order_sale(order, reservations=None, now=None):
    now = now or timezone.now()
    order = Order.objects.select_for_update().get(pk=order.pk)
    today = timezone.localdate(now)

    existing_document = InventoryDocument.objects.filter(
        source_order=order,
    ).first()

    if existing_document:
        if existing_document.status == "approved":
            return existing_document
        raise ValidationError(
            "An inventory sale document already exists for this order."
        )

    if order.status != "pending":
        raise ValidationError("Only pending orders can be recorded as sales.")

    if not order.reservation_expires_at or order.reservation_expires_at <= now:
        raise ValidationError("The order reservation has expired.")

    order_items = list(order.items.all().order_by("variant_id", "id"))

    expected_quantities = defaultdict(int)

    for item in order_items:
        if item.variant_id is None or item.quantity <= 0:
            raise ValidationError("The order contains an invalid item.")

        expected_quantities[item.variant_id] += item.quantity

    if not expected_quantities:
        raise ValidationError("The order has no valid items.")

    if reservations is None:
        reservations = list(
            order.stock_reservations.order_by("variant_id", "id")
        )
    else:
        reservations = list(reservations)

    reservations_by_variant = {}

    for reservation in reservations:
        if reservation.order_id != order.pk:
            raise ValidationError("A reservation belongs to another order.")

        if reservation.variant_id in reservations_by_variant:
            raise ValidationError("Duplicate reservation for an order variant.")

        reservations_by_variant[reservation.variant_id] = reservation

    actual_quantities = {
        variant_id: reservation.quantity
        for variant_id, reservation in reservations_by_variant.items()
    }

    if dict(expected_quantities) != actual_quantities:
        raise ValidationError("Order items and reservations do not match.")

    variant_ids = sorted(expected_quantities)

    # Lock variants before reservations and batches.
    from catalog.models import ProductVariant

    variants = list(
        ProductVariant.objects.select_for_update()
        .filter(id__in=variant_ids)
        .order_by("id")
    )

    if len(variants) != len(variant_ids):
        raise ValidationError("An order variant no longer exists.")

    locked_reservations = list(
        StockReservation.objects.select_for_update()
        .filter(
            order_id=order.pk,
            id__in=[reservation.id for reservation in reservations],
        )
        .order_by("variant_id", "id")
    )

    if len(locked_reservations) != len(reservations):
        raise ValidationError("An order reservation no longer exists.")

    for reservation in locked_reservations:
        if (
            reservation.status != "active"
            or reservation.expires_at <= now
        ):
            raise ValidationError("An order reservation is inactive or expired.")

    allocations = list(
        ReservationAllocation.objects.select_for_update()
        .filter(reservation__in=locked_reservations)
        .order_by("batch_id", "id")
    )

    allocations_by_reservation = defaultdict(list)

    reservations_by_id = {
        reservation.id: reservation
        for reservation in locked_reservations
    }

    for allocation in allocations:
        allocations_by_reservation[allocation.reservation_id].append(allocation)

    for reservation in locked_reservations:
        allocated_quantity = sum(
            allocation.quantity
            for allocation in allocations_by_reservation[reservation.id]
        )

        if allocated_quantity != reservation.quantity:
            raise ValidationError(
                "A reservation is not fully allocated to inventory batches."
            )

    batch_ids = sorted({allocation.batch_id for allocation in allocations})

    batches = list(
        InventoryBatch.objects.select_for_update()
        .filter(id__in=batch_ids)
        .order_by("id")
    )

    batches_by_id = {batch.id: batch for batch in batches}

    if len(batches_by_id) != len(batch_ids):
        raise ValidationError("An allocated inventory batch no longer exists.")

    for allocation in allocations:
        reservation = reservations_by_id[allocation.reservation_id]
        batch = batches_by_id[allocation.batch_id]
        if batch.variant_id != reservation.variant_id:
            raise ValidationError("A reservation allocation has an invalid batch.")

    allocated_by_batch = defaultdict(int)

    for allocation in allocations:
        allocated_by_batch[allocation.batch_id] += allocation.quantity

    active_allocations_by_batch = {
        row["batch_id"]: row["total"]
        for row in ReservationAllocation.objects.filter(
            batch_id__in=batch_ids,
            reservation__status="active",
            reservation__expires_at__gt=now,
            reservation__order__status="pending",
            reservation__order__reservation_expires_at__gt=now,
        ).values("batch_id").annotate(total=Sum("quantity"))
    }

    for batch_id, batch in batches_by_id.items():
        if (
            batch.status != "available"
            or (
                batch.expiration_date is not None
                and batch.expiration_date < today
            )
        ):
            raise ValidationError("An allocated inventory batch is unavailable.")

        physical = get_batch_physical_quantity(batch)
        active_allocations = active_allocations_by_batch.get(batch_id, 0)

        if physical < active_allocations:
            raise ValidationError(
                "Physical inventory is insufficient for active reservations."
            )

        if physical < allocated_by_batch[batch_id]:
            raise ValidationError("Physical inventory is insufficient for this sale.")

    document = InventoryDocument(
        document_number=f"SALE-{order.order_number}",
        document_type="outbound",
        status="draft",
        source_order=order,
        reference=order.order_number,
        reason="Online order sale",
        notes="Automatically generated after successful payment.",
        created_by_type="system",
        created_by=None,
    )
    document.full_clean()
    document.save()

    InventoryDocumentLog.objects.create(
        document=document,
        action="created",
        from_status="",
        to_status="draft",
        actor_type="system",
        actor=None,
        note="Online sale document created automatically.",
    )

    for reservation in locked_reservations:
        for allocation in allocations_by_reservation[reservation.id]:
            batch = batches_by_id[allocation.batch_id]

            item = InventoryDocumentItem(
                document=document,
                variant_id=reservation.variant_id,
                batch=batch,
                quantity=allocation.quantity,
                direction="outbound",
                reason="Online order sale",
            )
            item.full_clean()
            item.save()

            InventoryMovement.objects.create(
                batch=batch,
                document=document,
                document_item=item,
                movement_type="outbound",
                quantity_delta=-allocation.quantity,
                created_by_type="system",
                created_by=None,
                notes=f"Online sale: {order.order_number}",
            )

    for reservation in locked_reservations:
        reservation.status = "consumed"
        reservation.consumed_at = now
        reservation.save(update_fields=["status", "consumed_at"])

    document.status = "approved"
    document.approved_at = now
    document.save(
        update_fields=["status", "approved_at", "updated_at"],
        _allow_system_approval=True,
    )

    InventoryDocumentLog.objects.create(
        document=document,
        action="approved",
        from_status="draft",
        to_status="approved",
        actor_type="system",
        actor=None,
        note="Online sale document approved automatically.",
    )

    return document