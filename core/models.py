from django.db import models
from jalali_suite.models import JalaliDateTimeField


class Testimonial(models.Model):
    """Customer testimonial for homepage."""

    name = models.CharField(max_length=100, verbose_name="نام")
    role = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="نقش/عنوان",
        help_text="مثلاً: بدنساز حرفه‌ای، مربی باشگاه",
    )
    content = models.TextField(verbose_name="متن نظر")
    rating = models.PositiveSmallIntegerField(
        default=5,
        verbose_name="امتیاز (۱ تا ۵)",
        choices=[(i, str(i)) for i in range(1, 6)],
    )
    avatar = models.ImageField(
        upload_to="testimonials/",
        null=True,
        blank=True,
        verbose_name="عکس (اختیاری)",
        help_text="این عکس آواتر نظر دهنده است",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعال")
    order = models.PositiveIntegerField(default=0, verbose_name="ترتیب")
    created_at = JalaliDateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    class Meta:
        verbose_name = "نظر مشتری"
        verbose_name_plural = "نظرات مشتریان"
        ordering = ["order", "-created_at"]

    def __str__(self):
        return f"{self.name} - {self.rating}★"
