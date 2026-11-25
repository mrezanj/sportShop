from rest_framework import serializers

from users.models import Profile

from .models import InventoryDocument, InventoryDocumentItem, InventoryDocumentLog



ROLE_PERMISSIONS = (
    ("inventory.can_create_inventory_document", "ثبت‌کننده"),
    ("inventory.can_review_inventory_document", "حسابدار"),
    ("inventory.can_approve_inventory_document", "مدیر"),
)


def _person_info(user):
    if user is None:
        return None, None

    roles = [
        label
        for permission, label in ROLE_PERMISSIONS
        if user.has_perm(permission)
    ]
    can_view_reports = user.has_perm(
        "inventory.can_view_inventory_reports"
    )

    is_internal = user.is_staff or bool(roles) or can_view_reports

    if is_internal:
        display = user.get_full_name().strip() or user.username

        if roles:
            role = " / ".join(roles)
        elif can_view_reports:
            role = "مشاهده‌گر انبار"
        else:
            role = "کارمند"

        return display, role

    try:
        profile = user.profile
    except Profile.DoesNotExist:
        profile = None

    return (profile.mobile if profile else user.username), None


class InventoryDocumentListSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(
        source="created_by.username", read_only=True, allow_null=True
    )
    reviewed_by_username = serializers.CharField(
        source="reviewed_by.username", read_only=True, allow_null=True
    )
    approved_by_username = serializers.CharField(
        source="approved_by.username", read_only=True, allow_null=True
    )

    created_by_display = serializers.SerializerMethodField()
    created_by_role = serializers.SerializerMethodField()
    reviewed_by_display = serializers.SerializerMethodField()
    reviewed_by_role = serializers.SerializerMethodField()
    approved_by_display = serializers.SerializerMethodField()
    approved_by_role = serializers.SerializerMethodField()

    item_count = serializers.IntegerField(read_only=True)

    def get_created_by_display(self, obj):
        return _person_info(obj.created_by)[0]

    def get_created_by_role(self, obj):
        return _person_info(obj.created_by)[1]

    def get_reviewed_by_display(self, obj):
        return _person_info(obj.reviewed_by)[0]

    def get_reviewed_by_role(self, obj):
        return _person_info(obj.reviewed_by)[1]

    def get_approved_by_display(self, obj):
        return _person_info(obj.approved_by)[0]

    def get_approved_by_role(self, obj):
        return _person_info(obj.approved_by)[1]

    class Meta:
        model = InventoryDocument
        fields = [
            "id", "document_number", "document_type", "status", "reference",
            "source_order_id", "reason", "notes", "created_by_type",
            "created_by_id", "created_by_username", "created_by_display",
            "created_by_role", "reviewed_by_id", "reviewed_by_username",
            "reviewed_by_display", "reviewed_by_role", "reviewed_at",
            "approved_by_id", "approved_by_username", "approved_by_display",
            "approved_by_role", "approved_at", "item_count",
            "created_at", "updated_at",
        ]


class InventoryDocumentItemReadSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="variant.sku", read_only=True)
    product_name = serializers.CharField(source="variant.product.name_fa", read_only=True)
    batch_number = serializers.CharField(
        source="batch.batch_number", read_only=True, allow_null=True
    )
    batch_status = serializers.CharField(
        source="batch.status", read_only=True, allow_null=True
    )
    batch_expiration_date = serializers.DateField(
        source="batch.expiration_date", read_only=True, allow_null=True
    )

    class Meta:
        model = InventoryDocumentItem
        fields = [
            "id", "variant_id", "sku", "product_name", "batch_id",
            "batch_number", "batch_status", "batch_expiration_date",
            "new_batch_number", "new_batch_expiration_date", "quantity",
            "direction", "unit_cost", "reason",
        ]


class InventoryDocumentDetailSerializer(InventoryDocumentListSerializer):
    items = InventoryDocumentItemReadSerializer(many=True, read_only=True)

    class Meta(InventoryDocumentListSerializer.Meta):
        fields = InventoryDocumentListSerializer.Meta.fields + ["items"]


class InventoryDocumentLogSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(
        source="actor.username", read_only=True, allow_null=True
    )
    actor_display = serializers.SerializerMethodField()
    actor_role = serializers.SerializerMethodField()

    def get_actor_display(self, obj):
        return _person_info(obj.actor)[0]

    def get_actor_role(self, obj):
        return _person_info(obj.actor)[1]

    class Meta:
        model = InventoryDocumentLog
        fields = [
            "id", "action", "from_status", "to_status", "actor_type",
            "actor_id", "actor_username", "actor_display", "actor_role",
            "note", "created_at",
        ]
