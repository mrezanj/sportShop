from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.db import transaction

ROLE_PERMISSIONS = {
    "مدیر داخلی": [
        "inventory.can_approve_inventory_document",
        "inventory.can_view_inventory_reports",
        "orders.can_manage_order_status",
        "orders.can_manage_order_shipping_cost",
        "orders.can_manage_order_discrepancies",
        "orders.can_review_return_requests",
    ],
    "حسابدار": [
        "inventory.can_create_inventory_document",
        "inventory.can_review_inventory_document",
        "inventory.can_view_inventory_reports",
    ],
    "مشاور": [],
    "مشتری": [],
}

EXECUTIVE_GROUPS = ("مدیرعامل", "رئیس هیئت‌مدیره")
BUSINESS_APP_LABELS = ("catalog", "inventory", "orders", "payments", "cart", "core", "locations", "users")


class Command(BaseCommand):
    help = "Create/update standard SportShop staff groups and their operation permissions."

    @transaction.atomic
    def handle(self, *args, **options):
        groups = {}
        for name in (*EXECUTIVE_GROUPS, *ROLE_PERMISSIONS.keys()):
            groups[name], _ = Group.objects.get_or_create(name=name)

        # Executive groups receive permissions from business modules only. Django's
        # auth/user/group administration permissions are deliberately excluded.
        executive_permissions = Permission.objects.filter(
            content_type__app_label__in=BUSINESS_APP_LABELS
        ).exclude(
            content_type__model__in=("otpcode", "otpfailedattempt", "otprequestlimit")
        )
        for name in EXECUTIVE_GROUPS:
            groups[name].permissions.set(executive_permissions)

        for name, codenames in ROLE_PERMISSIONS.items():
            permissions = []
            for codename in codenames:
                app_label, permission_codename = codename.split(".", 1)
                permission = Permission.objects.filter(
                    content_type__app_label=app_label,
                    codename=permission_codename,
                ).first()
                if permission is None:
                    self.stderr.write(self.style.WARNING(f"Permission not found: {codename}"))
                    continue
                permissions.append(permission)
            groups[name].permissions.set(permissions)

        self.stdout.write(self.style.SUCCESS("Standard staff role groups configured."))
