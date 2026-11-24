from django.db import models
from orders.models import Order
from jalali_suite.models import JalaliDateTimeField
import uuid


class Payment(models.Model):
    STATUS_CHOICES = [
        ("initiating", "در حال شروع پرداخت"),
        ("verifying", "در حال تأیید پرداخت"),
        ("unknown", "وضعیت نامشخص"),
        ("pending", "در انتظار پرداخت"),
        ("success", "موفق"),
        ("failed", "ناموفق"),
        ("cancelled", "لغو شده"),
    ]

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    gateway = models.CharField(max_length=30, verbose_name="درگاه")
    request_key = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name="شناسه یکتای درخواست پرداخت",
    )
    request_started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان شروع درخواست به درگاه",
    )
    inquiry_started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان شروع استعلام وضعیت پرداخت",
    )

    verification_started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان شروع تأیید پرداخت",
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=0, verbose_name="مبلغ (تومان)"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", verbose_name="وضعیت"
    )
    authority = models.CharField(max_length=200, blank=True, verbose_name="شناسه درگاه")
    ref_id = models.CharField(max_length=100, blank=True, verbose_name="شماره پیگیری")
    gateway_response = models.JSONField(
        default=dict, blank=True, verbose_name="پاسخ درگاه"
    )
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "پرداخت"
        verbose_name_plural = "پرداخت‌ها"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.order.order_number} - {self.gateway} - {self.status}"

class MockGatewayTransaction(models.Model):
    STATUS_CHOICES = [
        ("pending", "در انتظار نتیجه"),
        ("success", "موفق"),
        ("failed", "ناموفق"),
    ]

    payment = models.OneToOneField(
        Payment,
        on_delete=models.CASCADE,
        related_name="mock_transaction",
        verbose_name="پرداخت",
    )
    authority = models.CharField(
        max_length=200,
        unique=True,
        verbose_name="شناسه تراکنش آزمایشی",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending",
        verbose_name="وضعیت تراکنش",
    )
    ref_id = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="شماره پیگیری",
    )
    raw_response = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="پاسخ خام درگاه",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="تاریخ ایجاد",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین به‌روزرسانی",
    )

    class Meta:
        verbose_name = "تراکنش درگاه آزمایشی"
        verbose_name_plural = "تراکنش‌های درگاه آزمایشی"

    def __str__(self):
        return f"{self.authority} - {self.status}"


class Refund(models.Model):
    STATUS_CHOICES = [
        ("requested", "درخواست‌شده"),
        ("approved", "تأییدشده"),
        ("processing", "در حال انجام"),
        ("succeeded", "انجام‌شده"),
        ("failed", "ناموفق"),
        ("rejected", "ردشده"),
    ]

    return_request = models.ForeignKey(
        "orders.ReturnRequest",
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name="درخواست مرجوعی",
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="refunds",
        verbose_name="پرداخت مبنا",
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        verbose_name="مبلغ بازپرداخت (تومان)",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="requested",
        verbose_name="وضعیت",
    )
    idempotency_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    provider_reference = models.CharField(max_length=200, blank=True, verbose_name="شناسه پیگیری ارائه‌دهنده")
    provider_response = models.JSONField(default=dict, blank=True, verbose_name="پاسخ ارائه‌دهنده")
    requested_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        related_name="requested_refunds",
    )
    processed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_refunds",
    )
    created_at = JalaliDateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "بازپرداخت"
        verbose_name_plural = "بازپرداخت‌ها"
        ordering = ["-created_at", "-id"]
        permissions = [
            ("can_manage_refunds", "Can manage refunds"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0),
                name="refund_amount_positive",
            ),
        ]

    def __str__(self):
        return f"{self.return_request.order.order_number} - {self.amount} - {self.status}"
