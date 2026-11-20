
from django.utils import timezone


def release_active_reservations(reservations, now=None):
    """
    Release active reservations.
    Expired reservations retain their expired status.
    """
    now = now or timezone.now()

    for reservation in reservations:
        if reservation.status != "active":
            continue

        reservation.status = (
            "expired" if reservation.expires_at <= now else "released"
        )
        reservation.released_at = now
        reservation.save(update_fields=["status", "released_at"])


def cancel_locked_order(order, reservations, now=None):
    """
    Cancel an order whose row and related inventory rows are already locked.
    """
    now = now or timezone.now()

    release_active_reservations(reservations, now)

    order.status = "cancelled"
    order.save(update_fields=["status", "updated_at"])
