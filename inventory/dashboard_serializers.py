from rest_framework import serializers

from users.models import Profile

from .models import InventoryDocument, InventoryDocumentItem, InventoryDocumentLog


OFFICIAL_STAFF_ROLES = (
    "مدیرعامل",
    "رئیس هیئت‌مدیره",
    "مدیر داخلی",
    "حسابدار",
    "ثبت‌کننده",
    "مشاور",
    "مشتری",
)


def _person_info(user):
    if user is None:
        return None, None

    # Display the person's actual official role, not a role inferred from
    # broad permissions. Executives intentionally hold several operational
    # permissions but must remain identified as CEO / Board Chair.
    if user.is_superuser:
        return user.get_full_name().strip() or user.username, "ادمین کل سیستم"

    roles = list(
        user.groups.filter(name__in=OFFICIAL_STAFF_ROLES)
        .order_by("name")
        .values_list("name", flat=True)
    )
    if roles:
        display = user.get_full_name().strip() or user.username
        # The staff-role workflow guarantees one official role. If legacy
        # data contains more than one, show the exact stored titles rather
        # than guessing from permissions or displaying a generic "مدیر".
        return display, " / ".join(roles)

    try:
        profile = user.profile
    except Profile.DoesNotExist:
        profile = None

    display = user.get_full_name().strip()
    if not display:
        display = profile.mobile if profile and profile.mobile else user.username
    return display, None


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
