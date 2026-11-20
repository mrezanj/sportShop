from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.models import ProductVariant
from orders.models import Order, StockReservation
from orders.services import cancel_locked_order
from payments.models import Payment


class Command(BaseCommand):
    help = "Expire unpaid orders and release their stock reservations."

    def handle(self, *args, **options):
        now = timezone.now()

        expired_order_ids = list(
            Order.objects.filter(
                status="pending",
                reservation_expires_at__isnull=False,
                reservation_expires_at__lte=now,
            )
            .order_by("id")
            .values_list("id", flat=True)
        )

        expired_count = 0
        cancelled_payment_count = 0

        for order_id in expired_order_ids:
            with transaction.atomic():
                order = (
                    Order.objects.select_for_update()
                    .filter(
                        pk=order_id,
                        status="pending",
                        reservation_expires_at__isnull=False,
                        reservation_expires_at__lte=now,
                    )
                    .first()
                )

                # The order may have been paid or cancelled meanwhile.
                if order is None:
                    continue

                variant_ids = list(
                    StockReservation.objects.filter(order=order)
                    .values_list("variant_id", flat=True)
                    .distinct()
                    .order_by("variant_id")
                )

                # Keep the same lock order as payment and manual cancellation.
                list(
                    ProductVariant.objects.select_for_update()
                    .filter(id__in=variant_ids)
                    .order_by("id")
                )

                reservations = list(
                    StockReservation.objects.select_for_update()
                    .filter(order=order)
                    .order_by("variant_id")
                )

                cancel_locked_order(
                    order,
                    reservations,
                    now,
                    note="لغو خودکار سفارش به علت پایان مهلت رزرو موجودی.",
                )

                updated_payments = Payment.objects.filter(
                    order=order,
                    status="pending",
                ).update(
                    status="cancelled",
                    gateway_response={"reason": "order_expired"},
                )

                cancelled_payment_count += updated_payments
                expired_count += 1

        self.stdout.write(self.style.SUCCESS(f"Expired orders: {expired_count}"))
        self.stdout.write(
            self.style.SUCCESS(f"Cancelled pending payments: {cancelled_payment_count}")
        )
