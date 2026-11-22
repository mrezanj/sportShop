from rest_framework.permissions import BasePermission


class CanViewInventoryReports(BasePermission):
    message = "You do not have permission to view inventory reports."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.has_perm(
                "inventory.can_view_inventory_reports"
            )
        )