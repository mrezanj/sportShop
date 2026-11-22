from django.db import models
from django.contrib.auth.models import User
from catalog.models import ProductVariant
from django.core.exceptions import ValidationError


class InventoryBatch(models.Model):
    STATUS_CHOICES = [
        ("available", "قابل فروش"),
        ("quarantined", "قرنطینه"),
        ("blocked", "غیرقابل فروش"),
    ]

    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="inventory_batches",
        verbose_name="تنوع محصول",
    )
    batch_number = models.CharField(
        max_length=100,
        verbose_name="شماره بچ",
    )
    expiration_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ انقضا",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="available",
        verbose_name="وضعیت",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_inventory_batches",
        verbose_name="ثبت‌کننده",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ثبت",
    )

    class Meta:
        verbose_name = "بچ انبار"
        verbose_name_plural = "بچ‌های انبار"
        constraints = [
            models.UniqueConstraint(
                fields=["variant", "batch_number"],
                name="unique_variant_batch_number",
            ),
        ]
        indexes = [
            models.Index(
                fields=["variant", "status"],
                name="inv_batch_variant_status_idx",
            ),
            models.Index(
                fields=["expiration_date"],
                name="inv_batch_expiration_idx",
            ),
        ]
        ordering = ["expiration_date", "id"]

    def __str__(self):
        return f"{self.variant.sku} - {self.batch_number}"


class InventoryDocumentQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(
            "Inventory documents must be changed through document services."
        )

    def delete(self):
        raise ValidationError("Inventory documents cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(
            "Inventory documents must be changed through document services."
        )


class InventoryDocument(models.Model):
    objects = InventoryDocumentQuerySet.as_manager()
    DOCUMENT_TYPES = [
        ("inbound", "ورود کالا"),
        ("outbound", "خروج کالا"),
        ("purchase", "خرید"),
        ("return", "مرجوعی"),
        ("waste", "ضایعات"),
        ("adjustment", "اصلاح موجودی"),
    ]

    STATUS_CHOICES = [
        ("draft", "پیش‌نویس"),
        ("pending_review", "در انتظار بررسی حسابدار"),
        ("pending_approval", "در انتظار تأیید مدیر داخلی"),
        ("approved", "تأیید نهایی"),
        ("rejected", "رد شده"),
        ("cancelled", "لغو شده"),
    ]

    document_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="شماره سند",
    )
    document_type = models.CharField(
        max_length=20,
        choices=DOCUMENT_TYPES,
        verbose_name="نوع سند",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
        verbose_name="وضعیت",
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="شماره مرجع",
    )
    reason = models.TextField(
        blank=True,
        verbose_name="دلیل عملیات",
    )
    notes = models.TextField(
        blank=True,
        verbose_name="توضیحات",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_inventory_documents",
        verbose_name="ثبت‌کننده",
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reviewed_inventory_documents",
        verbose_name="بررسی‌کننده حسابدار",
    )
    approved_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_inventory_documents",
        verbose_name="تأییدکننده مدیر داخلی",
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان بررسی",
    )
    approved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان تأیید نهایی",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان ثبت",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین بروزرسانی",
    )

    class Meta:
        verbose_name = "سند انبار"
        verbose_name_plural = "اسناد انبار"
        ordering = ["-created_at"]
        permissions = [
            (
                "can_create_inventory_document",
                "Can create inventory documents",
            ),
            (
                "can_review_inventory_document",
                "Can review inventory documents",
            ),
            (
                "can_approve_inventory_document",
                "Can approve inventory documents",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "created_at"],
                name="inv_doc_status_created_idx",
            ),
            models.Index(
                fields=["document_type", "created_at"],
                name="inv_doc_type_created_idx",
            ),
        ]

    def __str__(self):
        return self.document_number

    def save(self, *args, **kwargs):
        allow_transition = kwargs.pop("_allow_transition", False)

        if self.pk:
            if not allow_transition:
                raise ValidationError(
                    "Inventory documents must be changed through document services."
                )

            allowed_fields = {
                "status",
                "reviewed_by",
                "reviewed_at",
                "approved_by",
                "approved_at",
                "updated_at",
            }

            update_fields = kwargs.get("update_fields")

            if not update_fields or not set(update_fields).issubset(allowed_fields):
                raise ValidationError("Only document workflow fields can be changed.")

            original = type(self).objects.get(pk=self.pk)

            valid_transitions = {
                "draft": {"pending_review"},
                "pending_review": {"pending_approval", "rejected"},
                "pending_approval": {"approved", "rejected"},
            }

            if self.status not in valid_transitions.get(original.status, set()):
                raise ValidationError("Invalid inventory document status transition.")

        elif self.status != "draft":
            raise ValidationError("New inventory documents must start as draft.")

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Inventory documents cannot be deleted.")


class InventoryDocumentItemQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(
            "Inventory document items must be changed through document services."
        )

    def delete(self):
        if self.exclude(document__status="draft").exists():
            raise ValidationError("Items of non-draft documents cannot be deleted.")

        return super().delete()

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(
            "Inventory document items must be changed through document services."
        )


class InventoryDocumentItem(models.Model):
    objects = InventoryDocumentItemQuerySet.as_manager()
    document = models.ForeignKey(
        InventoryDocument,
        on_delete=models.PROTECT,
        related_name="items",
        verbose_name="سند انبار",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="inventory_document_items",
        verbose_name="تنوع محصول",
    )
    batch = models.ForeignKey(
        InventoryBatch,
        on_delete=models.PROTECT,
        related_name="document_items",
        null=True,
        blank=True,
        verbose_name="بچ",
    )
    new_batch_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="شماره بچ جدید",
    )
    new_batch_expiration_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ انقضای بچ جدید",
    )
    quantity = models.PositiveIntegerField(
        verbose_name="تعداد",
    )
    DIRECTION_CHOICES = [
        ("inbound", "Inbound"),
        ("outbound", "Outbound"),
    ]

    direction = models.CharField(
        max_length=10,
        choices=DIRECTION_CHOICES,
        default="inbound",
        verbose_name="جهت عملیات",
    )
    unit_cost = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        null=True,
        blank=True,
        verbose_name="بهای واحد (تومان)",
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="دلیل ردیف",
    )

    class Meta:
        verbose_name = "ردیف سند انبار"
        verbose_name_plural = "ردیف‌های سند انبار"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="inv_doc_item_quantity_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["variant", "document"],
                name="inv_item_variant_doc_idx",
            ),
        ]

    def __str__(self):
        return f"{self.variant.sku} - {self.quantity}"

    def save(self, *args, **kwargs):
        if self.document.status != "draft":
            raise ValidationError("Items of non-draft documents cannot be modified.")

        if self.pk:
            original = type(self).objects.filter(pk=self.pk).first()

            if original and original.document.status != "draft":
                raise ValidationError(
                    "Items of non-draft documents cannot be modified."
                )

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if (
            type(self)
            .objects.filter(
                pk=self.pk,
            )
            .exclude(
                document__status="draft",
            )
            .exists()
        ):
            raise ValidationError("Items of non-draft documents cannot be deleted.")

        return super().delete(*args, **kwargs)


class InventoryMovementQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Inventory movements are immutable.")

    def delete(self):
        raise ValidationError("Inventory movements cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Inventory movements are immutable.")


class InventoryMovement(models.Model):
    objects = InventoryMovementQuerySet.as_manager()
    MOVEMENT_TYPES = [
        ("inbound", "ورود"),
        ("outbound", "خروج"),
        ("return", "مرجوعی"),
        ("waste", "ضایعات"),
        ("adjustment", "اصلاح موجودی"),
        ("reversal", "گردش معکوس"),
    ]

    batch = models.ForeignKey(
        InventoryBatch,
        on_delete=models.PROTECT,
        related_name="movements",
        verbose_name="بچ",
    )
    document = models.ForeignKey(
        InventoryDocument,
        on_delete=models.PROTECT,
        related_name="movements",
        verbose_name="سند انبار",
    )
    document_item = models.ForeignKey(
        InventoryDocumentItem,
        on_delete=models.PROTECT,
        related_name="movements",
        verbose_name="ردیف سند",
    )
    movement_type = models.CharField(
        max_length=20,
        choices=MOVEMENT_TYPES,
        verbose_name="نوع گردش",
    )
    quantity_delta = models.IntegerField(
        verbose_name="تغییر موجودی",
        help_text="ورود مثبت و خروج منفی ثبت می‌شود.",
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="created_inventory_movements",
        verbose_name="ثبت‌کننده",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان ثبت",
    )
    notes = models.TextField(
        blank=True,
        verbose_name="توضیحات",
    )

    class Meta:
        verbose_name = "گردش موجودی"
        verbose_name_plural = "گردش‌های موجودی"
        ordering = ["created_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(quantity_delta=0),
                name="inv_movement_quantity_nonzero",
            ),
        ]
        indexes = [
            models.Index(
                fields=["batch", "created_at"],
                name="inv_move_batch_created_idx",
            ),
            models.Index(
                fields=["document", "created_at"],
                name="inv_move_doc_created_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Inventory movements are immutable.")

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Inventory movements cannot be deleted.")

    def __str__(self):
        return f"{self.batch.batch_number} - " f"{self.quantity_delta:+d}"


class ReservationAllocation(models.Model):
    reservation = models.ForeignKey(
        "orders.StockReservation",
        on_delete=models.PROTECT,
        related_name="batch_allocations",
        verbose_name="رزرو سفارش",
    )
    batch = models.ForeignKey(
        InventoryBatch,
        on_delete=models.PROTECT,
        related_name="reservation_allocations",
        verbose_name="بچ",
    )
    quantity = models.PositiveIntegerField(
        verbose_name="تعداد تخصیص‌یافته",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان تخصیص",
    )

    class Meta:
        verbose_name = "تخصیص رزرو به بچ"
        verbose_name_plural = "تخصیص‌های رزرو به بچ"
        constraints = [
            models.UniqueConstraint(
                fields=["reservation", "batch"],
                name="unique_reservation_batch",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="inv_allocation_quantity_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["batch", "created_at"],
                name="inv_alloc_batch_created_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.reservation.order.order_number} - "
            f"{self.batch.batch_number} - {self.quantity}"
        )


class InventoryStockThreshold(models.Model):
    variant = models.OneToOneField(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="inventory_threshold",
        verbose_name="تنوع محصول",
    )
    minimum_quantity = models.PositiveIntegerField(
        default=0,
        verbose_name="حداقل موجودی",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="updated_inventory_thresholds",
        null=True,
        blank=True,
        verbose_name="آخرین ویرایش‌کننده",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین بروزرسانی",
    )

    class Meta:
        verbose_name = "حداقل موجودی SKU"
        verbose_name_plural = "حداقل موجودی SKUها"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(minimum_quantity__gte=0),
                name="inv_threshold_quantity_nonnegative",
            ),
        ]

    def __str__(self):
        return f"{self.variant.sku} - حداقل: {self.minimum_quantity}"


class InventoryDocumentLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Inventory document logs are immutable.")

    def delete(self):
        raise ValidationError("Inventory document logs cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError("Inventory document logs are immutable.")


class InventoryDocumentLog(models.Model):
    objects = InventoryDocumentLogQuerySet.as_manager()
    ACTION_CHOICES = [
        ("created", "ایجاد سند"),
        ("submitted", "ارسال برای بررسی"),
        ("reviewed", "بررسی حسابدار"),
        ("approved", "تأیید نهایی"),
        ("rejected", "رد سند"),
        ("cancelled", "لغو سند"),
    ]

    document = models.ForeignKey(
        InventoryDocument,
        on_delete=models.PROTECT,
        related_name="history",
        verbose_name="سند انبار",
    )
    action = models.CharField(
        max_length=20,
        choices=ACTION_CHOICES,
        verbose_name="نوع اقدام",
    )
    from_status = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="وضعیت قبلی",
    )
    to_status = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="وضعیت جدید",
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="inventory_document_logs",
        verbose_name="انجام‌دهنده",
    )
    note = models.TextField(
        blank=True,
        verbose_name="توضیحات",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان اقدام",
    )

    class Meta:
        verbose_name = "تاریخچه سند انبار"
        verbose_name_plural = "تاریخچه اسناد انبار"
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(
                fields=["document", "created_at"],
                name="inv_doc_log_created_idx",
            ),
            models.Index(
                fields=["actor", "created_at"],
                name="inv_doc_log_actor_idx",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Inventory document logs are immutable.")

        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Inventory document logs cannot be deleted.")

    def __str__(self):
        return f"{self.document.document_number} - {self.get_action_display()}"
