from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import OTPFailedAttempt


class Command(BaseCommand):
    help = "Delete OTP failed-attempt records older than one hour."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=1)

        deleted_count, _ = OTPFailedAttempt.objects.filter(
            created_at__lt=cutoff,
        ).delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted {deleted_count} old OTP failed-attempt record(s)."
            )
        )