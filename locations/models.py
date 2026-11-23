
from django.db import models


class Province(models.Model):
    slug = models.SlugField(
        max_length=30,
        unique=True,
        verbose_name="شناسه استان",
    )
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="نام استان",
    )
    source_code = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="کد استان در منبع",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال",
    )

    class Meta:
        verbose_name = "استان"
        verbose_name_plural = "استان‌ها"
        ordering = ["name"]

    def __str__(self):
        return self.name


class City(models.Model):
    province = models.ForeignKey(
        Province,
        on_delete=models.PROTECT,
        related_name="cities",
        verbose_name="استان",
    )
    code = models.CharField(
        max_length=10,
        unique=True,
        verbose_name="کد شهر در منبع",
    )
    name = models.CharField(
        max_length=150,
        verbose_name="نام شهر",
    )
    county_name = models.CharField(
        max_length=150,
        verbose_name="نام شهرستان",
    )
    district_name = models.CharField(
        max_length=150,
        verbose_name="نام بخش",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال",
    )

    class Meta:
        verbose_name = "شهر"
        verbose_name_plural = "شهرها"
        ordering = ["province__name", "name", "county_name"]
        indexes = [
            models.Index(
                fields=["province", "is_active", "name"],
                name="location_city_prov_active_idx",
            ),
        ]

    def __str__(self):
        return f"{self.name} - {self.county_name} - {self.province.name}"
