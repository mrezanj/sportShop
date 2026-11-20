from django.db import models
from orders.models import Order
from jalali_suite.models import JalaliDateTimeField

class Payment(models.Model):
    STATUS_CHOICES = [
        ('pending', 'در انتظار پرداخت'),
        ('success', 'موفق'),
        ('failed', 'ناموفق'),
        ('cancelled', 'لغو شده'),
    ]

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name='payments'
    )
    gateway = models.CharField(max_length=30, verbose_name='درگاه')
    amount = models.DecimalField(
        max_digits=12, decimal_places=0, verbose_name='مبلغ (تومان)'
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default='pending',
        verbose_name='وضعیت'
    )
    authority = models.CharField(
        max_length=200, blank=True, verbose_name='شناسه درگاه'
    )
    ref_id = models.CharField(
        max_length=100, blank=True, verbose_name='شماره پیگیری'
    )
    gateway_response = models.JSONField(
        default=dict, blank=True, verbose_name='پاسخ درگاه'
    )
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'پرداخت'
        verbose_name_plural = 'پرداخت‌ها'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.order.order_number} - {self.gateway} - {self.status}'