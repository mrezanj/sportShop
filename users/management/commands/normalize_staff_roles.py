from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction


OFFICIAL_ROLES = (
    "مدیرعامل",
    "رئیس هیئت‌مدیره",
    "مدیر داخلی",
    "حسابدار",
    "مشاور",
    "مشتری",
)


class Command(BaseCommand):
    help = (
        "Normalize non-superuser accounts to exactly one official SportShop role, "
        "remove legacy group memberships and direct permissions, and preserve superusers."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        # Ensure the official groups and their permissions are authoritative first.
        call_command("setup_staff_roles")

        role_groups = {
            group.name: group
            for group in Group.objects.filter(name__in=OFFICIAL_ROLES)
        }
        customer_group = role_groups["مشتری"]

        normalized = 0
        unchanged = 0
        protected = 0

        users = User.objects.select_for_update().prefetch_related(
            "groups", "user_permissions"
        ).order_by("pk")

        for user in users:
            if user.is_superuser:
                protected += 1
                continue

            current_groups = list(user.groups.all())
            current_roles = [
                group for group in current_groups
                if group.name in OFFICIAL_ROLES
            ]

            # A single explicit official role is retained. Accounts with no
            # role or conflicting multiple roles safely fall back to customer.
            if len(current_roles) == 1:
                selected_role = current_roles[0]
            else:
                selected_role = customer_group

            already_normalized = (
                len(current_groups) == 1
                and current_groups[0].pk == selected_role.pk
                and not user.user_permissions.exists()
            )
            if already_normalized:
                unchanged += 1
                continue

            user.groups.set([selected_role])
            user.user_permissions.clear()
            normalized += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Role normalization complete: "
                f"{normalized} updated, {unchanged} already normalized, "
                f"{protected} superuser account(s) protected."
            )
        )
