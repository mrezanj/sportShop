from django.contrib.auth.models import Group, Permission
from django.core.management import call_command
from django.test import TestCase


class StaffRoleSetupCommandTests(TestCase):
    def test_command_is_idempotent_and_creates_roles(self):
        call_command("setup_staff_roles")
        call_command("setup_staff_roles")

        expected = {
            "مدیرعامل",
            "رئیس هیئت‌مدیره",
            "مدیر داخلی",
            "حسابدار",
            "مشاور",
            "مشتری",
        }
        self.assertTrue(expected.issubset(set(Group.objects.values_list("name", flat=True))))
        self.assertEqual(Group.objects.filter(name__in=expected).count(), len(expected))

    def test_executive_groups_receive_business_permissions_not_auth_admin(self):
        call_command("setup_staff_roles")
        ceo = Group.objects.get(name="مدیرعامل")
        chair = Group.objects.get(name="رئیس هیئت‌مدیره")

        self.assertEqual(set(ceo.permissions.values_list("id", flat=True)),
                         set(chair.permissions.values_list("id", flat=True)))
        self.assertTrue(ceo.permissions.filter(content_type__app_label="catalog").exists())
        self.assertFalse(ceo.permissions.filter(content_type__app_label="auth").exists())

    def test_accountant_and_internal_manager_permissions_are_separated(self):
        call_command("setup_staff_roles")
        accountant = Group.objects.get(name="حسابدار")
        internal = Group.objects.get(name="مدیر داخلی")

        self.assertTrue(accountant.permissions.filter(codename="can_review_inventory_document").exists())
        self.assertFalse(accountant.permissions.filter(codename="can_approve_inventory_document").exists())
        self.assertTrue(internal.permissions.filter(codename="can_approve_inventory_document").exists())
        self.assertFalse(internal.permissions.filter(codename="can_review_inventory_document").exists())
