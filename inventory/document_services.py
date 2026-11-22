from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from catalog.models import ProductVariant
from orders.models import StockReservation

from .models import (
    InventoryBatch,
    InventoryDocument,
    InventoryDocumentItem,
    InventoryDocumentLog,
    InventoryMovement,
    ReservationAllocation,
)


def _require_permission(user, permission):
    if not user or not user.is_authenticated:
        raise PermissionDenied("Authentication is required.")

    if not user.has_perm(permission):
        raise PermissionDenied("You do not have permission to perform this action.")


def _log_document_action(
    document,
    action,
    actor,
    from_status="",
    to_status="",
    note="",
):
    InventoryDocumentLog.objects.create(
        document=document,
        action=action,
        actor=actor,
        from_status=from_status,
        to_status=to_status,
        note=note,
    )


def _save_document_transition(document, update_fields):
    document.save(
        update_fields=update_fields,
        _allow_transition=True,
    )


@transaction.atomic
def create_inventory_document(
    *,
    user,
    document_number,
    document_type,
    reason="",
    reference="",
    notes="",
):
    _require_permission(
        user,
        "inventory.can_create_inventory_document",
    )

    valid_types = {value for value, label in InventoryDocument.DOCUMENT_TYPES}

    if document_type not in valid_types:
        raise ValidationError("Invalid inventory document type.")

    document = InventoryDocument(
        document_number=document_number,
        document_type=document_type,
        status="draft",
        reason=reason,
        reference=reference,
        notes=notes,
        created_by=user,
    )

    document.full_clean()
    document.save()

    _log_document_action(
        document=document,
        action="created",
        actor=user,
        to_status="draft",
    )

    return document


@transaction.atomic
def add_inventory_document_item(
    *,
    user,
    document_id,
    variant,
    quantity,
    direction,
    batch=None,
    new_batch_number="",
    new_batch_expiration_date=None,
    unit_cost=None,
    reason="",
):
    _require_permission(
        user,
        "inventory.can_create_inventory_document",
    )

    document = InventoryDocument.objects.select_for_update().get(
        pk=document_id,
    )

    if document.status != "draft":
        raise ValidationError("Only draft documents can be edited.")

    if document.created_by_id != user.id:
        raise PermissionDenied("Only the document creator can edit it.")

    if quantity <= 0:
        raise ValidationError("Quantity must be greater than zero.")

    if direction not in {"inbound", "outbound"}:
        raise ValidationError("Invalid operation direction.")
    if (
        new_batch_expiration_date is not None
        and new_batch_expiration_date < timezone.localdate()
    ):
        raise ValidationError("Batch expiration date cannot be in the past.")
    inbound_types = {"inbound", "purchase", "return"}
    outbound_types = {"outbound", "waste"}

    if document.document_type in inbound_types and direction != "inbound":
        raise ValidationError("This document type requires inbound direction.")

    if document.document_type in outbound_types and direction != "outbound":
        raise ValidationError("This document type requires outbound direction.")

    if document.document_type == "return":
        if batch is not None or not new_batch_number:
            raise ValidationError("Returned goods must be assigned to a new batch.")

    if batch is not None:
        if batch.variant_id != variant.id:
            raise ValidationError("The selected batch belongs to another SKU.")

        if new_batch_number or new_batch_expiration_date is not None:
            raise ValidationError(
                "When selecting an existing batch, do not provide new batch information."
            )

    if direction == "outbound" and (
        new_batch_number or new_batch_expiration_date is not None
    ):
        raise ValidationError("Outbound items cannot define new batch information.")

    if direction == "inbound" and batch is None and not new_batch_number:
        raise ValidationError(
            "Inbound items require an existing batch or a new batch number."
        )

    if new_batch_number:
        if InventoryBatch.objects.filter(
            variant=variant,
            batch_number=new_batch_number,
        ).exists():
            raise ValidationError("This batch number already exists for this SKU.")
        if InventoryDocumentItem.objects.filter(
            document=document,
            variant=variant,
            new_batch_number=new_batch_number,
        ).exists():
            raise ValidationError(
                "The same batch number cannot appear twice in one document."
            )
    item = InventoryDocumentItem(
        document=document,
        variant=variant,
        batch=batch,
        new_batch_number=new_batch_number,
        new_batch_expiration_date=new_batch_expiration_date,
        quantity=quantity,
        direction=direction,
        unit_cost=unit_cost,
        reason=reason,
    )

    item.full_clean()
    item.save()

    return item


@transaction.atomic
def submit_inventory_document(*, user, document_id):
    _require_permission(
        user,
        "inventory.can_create_inventory_document",
    )

    document = InventoryDocument.objects.select_for_update().get(
        pk=document_id,
    )

    if document.status != "draft":
        raise ValidationError("Only draft documents can be submitted.")

    if document.created_by_id != user.id:
        raise PermissionDenied("Only the document creator can submit it.")

    items = list(
        InventoryDocumentItem.objects.filter(
            document=document,
        ).select_related("variant", "batch")
    )

    if not items:
        raise ValidationError("A document must contain at least one item.")

    if document.document_type == "adjustment" and not document.reason.strip():
        raise ValidationError("An adjustment document requires a reason.")
    seen_new_batches = set()

    inbound_types = {"inbound", "purchase", "return"}
    outbound_types = {"outbound", "waste"}

    seen_new_batches = set()

    for item in items:
        if item.direction not in {"inbound", "outbound"}:
            raise ValidationError("Invalid operation direction.")

        if document.document_type in inbound_types and item.direction != "inbound":
            raise ValidationError("This document type requires inbound direction.")

        if document.document_type in outbound_types and item.direction != "outbound":
            raise ValidationError("This document type requires outbound direction.")

        if document.document_type == "return":
            if item.batch_id is not None or not item.new_batch_number:
                raise ValidationError("Returned goods must be assigned to a new batch.")

        if item.batch_id is not None:
            if item.batch.variant_id != item.variant_id:
                raise ValidationError("The selected batch belongs to another SKU.")

            if item.new_batch_number or item.new_batch_expiration_date is not None:
                raise ValidationError(
                    "An existing batch cannot include new batch information."
                )

        if item.direction == "inbound":
            if item.batch is None and not item.new_batch_number:
                raise ValidationError(
                    f"SKU {item.variant.sku} requires batch information."
                )

        if item.direction == "outbound" and (
            item.new_batch_number or item.new_batch_expiration_date is not None
        ):
            raise ValidationError("Outbound items cannot define new batch information.")

        if (
            item.new_batch_expiration_date is not None
            and item.new_batch_expiration_date < timezone.localdate()
        ):
            raise ValidationError("Batch expiration date cannot be in the past.")

        if item.new_batch_number:
            batch_key = (item.variant_id, item.new_batch_number)

            if batch_key in seen_new_batches:
                raise ValidationError(
                    "The same new batch cannot appear twice in one document."
                )

            if InventoryBatch.objects.filter(
                variant_id=item.variant_id,
                batch_number=item.new_batch_number,
            ).exists():
                raise ValidationError("This batch number already exists for this SKU.")

            seen_new_batches.add(batch_key)

    document.status = "pending_review"
    _save_document_transition(
        document,
        ["status", "updated_at"],
    )

    _log_document_action(
        document=document,
        action="submitted",
        actor=user,
        from_status="draft",
        to_status="pending_review",
    )

    return document


@transaction.atomic
def review_inventory_document(
    *,
    user,
    document_id,
    note="",
):
    _require_permission(
        user,
        "inventory.can_review_inventory_document",
    )

    document = InventoryDocument.objects.select_for_update().get(
        pk=document_id,
    )

    if document.status != "pending_review":
        raise ValidationError("Only documents pending review can be reviewed.")

    if document.created_by_id == user.id:
        raise PermissionDenied("The document creator cannot review the same document.")

    document.status = "pending_approval"
    document.reviewed_by = user
    document.reviewed_at = timezone.now()

    _save_document_transition(
        document,
        ["status", "reviewed_by", "reviewed_at", "updated_at"],
    )

    _log_document_action(
        document=document,
        action="reviewed",
        actor=user,
        from_status="pending_review",
        to_status="pending_approval",
        note=note,
    )

    return document


@transaction.atomic
def reject_inventory_document(
    *,
    user,
    document_id,
    note,
):
    if not note or not note.strip():
        raise ValidationError("A rejection reason is required.")

    document = InventoryDocument.objects.select_for_update().get(
        pk=document_id,
    )

    if document.status == "pending_review":
        _require_permission(
            user,
            "inventory.can_review_inventory_document",
        )

        if document.created_by_id == user.id:
            raise PermissionDenied(
                "The document creator cannot reject the same document."
            )

    elif document.status == "pending_approval":
        _require_permission(
            user,
            "inventory.can_approve_inventory_document",
        )

        if document.reviewed_by_id == user.id:
            raise PermissionDenied(
                "The reviewer cannot reject the same document at approval stage."
            )

    else:
        raise ValidationError(
            "Only documents pending review or approval can be rejected."
        )

    old_status = document.status

    document.status = "rejected"
    _save_document_transition(
        document,
        ["status", "updated_at"],
    )

    _log_document_action(
        document=document,
        action="rejected",
        actor=user,
        from_status=old_status,
        to_status="rejected",
        note=note.strip(),
    )

    return document


def _get_batch_quantities(batch, now):
    physical = (
        InventoryMovement.objects.filter(batch=batch).aggregate(
            total=Sum("quantity_delta"),
        )["total"]
        or 0
    )

    allocated = (
        ReservationAllocation.objects.filter(
            batch=batch,
            reservation__status="active",
            reservation__expires_at__gt=now,
            reservation__order__status="pending",
            reservation__order__reservation_expires_at__gt=now,
        ).aggregate(total=Sum("quantity"),)["total"]
        or 0
    )

    return physical, allocated


def _get_variant_reserved_quantity(variant, now):
    return (
        StockReservation.objects.filter(
            variant=variant,
            status="active",
            expires_at__gt=now,
            order__status="pending",
            order__reservation_expires_at__gt=now,
        ).aggregate(total=Sum("quantity"),)["total"]
        or 0
    )


def _approve_inbound_item(item, user, now):
    if (
        item.new_batch_expiration_date
        and item.new_batch_expiration_date < timezone.localdate()
    ):
        raise ValidationError("Cannot create a batch with an expired date.")
    if item.batch_id:
        batch = InventoryBatch.objects.select_for_update().get(
            pk=item.batch_id,
        )

        if batch.variant_id != item.variant_id:
            raise ValidationError("The selected batch belongs to another SKU.")

        if batch.status != "available":
            raise ValidationError("The selected batch is not available.")

        if batch.expiration_date and batch.expiration_date < timezone.localdate():
            raise ValidationError("Cannot add stock to an expired batch.")

    else:
        if (
            item.new_batch_expiration_date
            and item.new_batch_expiration_date < timezone.localdate()
        ):
            raise ValidationError("Cannot create a batch with an expired date.")
        batch, created = InventoryBatch.objects.get_or_create(
            variant=item.variant,
            batch_number=item.new_batch_number,
            defaults={
                "expiration_date": item.new_batch_expiration_date,
                "status": (
                    "quarantined"
                    if item.document.document_type == "return"
                    else "available"
                ),
                "created_by": user,
            },
        )

        if not created:
            raise ValidationError("The batch number already exists for this SKU.")

    movement_type = {
        "inbound": "inbound",
        "purchase": "inbound",
        "return": "return",
        "adjustment": "adjustment",
    }[item.document.document_type]

    InventoryMovement.objects.create(
        batch=batch,
        document=item.document,
        document_item=item,
        movement_type=movement_type,
        quantity_delta=item.quantity,
        created_by=user,
    )


def _approve_outbound_item(item, user, now):
    from django.db.models import F, Q

    today = timezone.localdate()

    batches_query = InventoryBatch.objects.select_for_update().filter(
        variant_id=item.variant_id,
    )

    if item.document.document_type != "waste":
        batches_query = batches_query.filter(
            status="available",
        ).filter(Q(expiration_date__isnull=True) | Q(expiration_date__gte=today))

    batches = list(
        batches_query.order_by(
            F("expiration_date").asc(nulls_last=True),
            "id",
        )
    )

    if item.batch_id:
        batches = [batch for batch in batches if batch.id == item.batch_id]

        if not batches:
            raise ValidationError("The selected batch is not available for outbound.")

    reserved = _get_variant_reserved_quantity(item.variant, now)

    allocated_total = (
        ReservationAllocation.objects.filter(
            batch__variant_id=item.variant_id,
            reservation__status="active",
            reservation__expires_at__gt=now,
            reservation__order__status="pending",
            reservation__order__reservation_expires_at__gt=now,
        ).aggregate(total=Sum("quantity"),)["total"]
        or 0
    )

    unallocated_reserved = max(reserved - allocated_total, 0)

    if item.batch_id and unallocated_reserved:
        raise ValidationError(
            "This SKU has reservations not assigned to specific batches. "
            "Use automatic FEFO allocation instead."
        )

    remaining = item.quantity

    for batch in batches:
        physical, allocated = _get_batch_quantities(batch, now)
        batch_available = max(physical - allocated, 0)

        if unallocated_reserved:
            protected = min(batch_available, unallocated_reserved)
            batch_available -= protected
            unallocated_reserved -= protected

        quantity = min(batch_available, remaining)

        if quantity <= 0:
            continue

        InventoryMovement.objects.create(
            batch=batch,
            document=item.document,
            document_item=item,
            movement_type=(
                "waste"
                if item.document.document_type == "waste"
                else (
                    "adjustment"
                    if item.document.document_type == "adjustment"
                    else "outbound"
                )
            ),
            quantity_delta=-quantity,
            created_by=user,
        )

        remaining -= quantity

        if remaining == 0:
            break

    if remaining:
        raise ValidationError(
            f"Insufficient unreserved batch stock for SKU {item.variant.sku}."
        )


@transaction.atomic
def approve_inventory_document(*, user, document_id, note=""):
    _require_permission(
        user,
        "inventory.can_approve_inventory_document",
    )

    document = InventoryDocument.objects.select_for_update().get(
        pk=document_id,
    )

    if document.status != "pending_approval":
        raise ValidationError("Only documents pending approval can be approved.")

    if document.reviewed_by_id == user.id:
        raise PermissionDenied("The reviewer cannot approve the same document.")

    if document.created_by_id == user.id:
        raise PermissionDenied("The document creator cannot approve the same document.")

    items = list(
        InventoryDocumentItem.objects.filter(
            document=document,
        )
        .select_related("variant", "batch")
        .order_by("variant_id", "id")
    )

    if not items:
        raise ValidationError("The document has no items.")
    seen_new_batches = set()

    for item in items:
        if item.new_batch_number:
            batch_key = (item.variant_id, item.new_batch_number)

            if batch_key in seen_new_batches:
                raise ValidationError(
                    "The same new batch cannot appear twice in one document."
                )

            seen_new_batches.add(batch_key)

            if InventoryBatch.objects.filter(
                variant_id=item.variant_id,
                batch_number=item.new_batch_number,
            ).exists():
                raise ValidationError("The batch number already exists for this SKU.")
    variant_ids = sorted({item.variant_id for item in items})

    list(
        ProductVariant.objects.select_for_update()
        .filter(id__in=variant_ids)
        .order_by("id")
        .values_list("id", flat=True)
    )

    now = timezone.now()

    for item in items:
        if (
            item.new_batch_expiration_date is not None
            and item.new_batch_expiration_date < timezone.localdate()
        ):
            raise ValidationError("Cannot approve an item with an expired batch date.")
        if document.document_type == "return":
            if item.batch_id is not None or not item.new_batch_number:
                raise ValidationError("Returned goods must be assigned to a new batch.")
        if item.direction == "inbound":
            if document.document_type in {"outbound", "waste"}:
                raise ValidationError("This document type requires outbound direction.")

            _approve_inbound_item(item, user, now)

        elif item.direction == "outbound":
            if document.document_type in {"inbound", "purchase", "return"}:
                raise ValidationError("This document type requires inbound direction.")

            _approve_outbound_item(item, user, now)

        else:
            raise ValidationError("Invalid item direction.")

    document.status = "approved"
    document.approved_by = user
    document.approved_at = now

    _save_document_transition(
        document,
        ["status", "approved_by", "approved_at", "updated_at"],
    )

    _log_document_action(
        document=document,
        action="approved",
        actor=user,
        from_status="pending_approval",
        to_status="approved",
        note=note,
    )

    return document
