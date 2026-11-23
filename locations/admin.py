
from django.contrib import admin

from .models import Province, City


@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "slug",
        "source_code",
        "is_active",
        "city_count",
    )
    search_fields = (
        "name",
        "slug",
        "source_code",
    )
    list_filter = (
        "is_active",
    )
    ordering = (
        "name",
    )
    readonly_fields = (
        "slug",
        "name",
        "source_code",
    )
    list_per_page = 50

    @admin.display(description="تعداد شهرها")
    def city_count(self, obj):
        return obj.cities.count()


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "county_name",
        "district_name",
        "province",
        "code",
        "is_active",
    )
    search_fields = (
        "name",
        "county_name",
        "district_name",
        "code",
        "province__name",
    )
    list_filter = (
        "province",
        "is_active",
    )
    ordering = (
        "province__name",
        "name",
        "county_name",
    )
    readonly_fields = (
        "code",
        "name",
        "county_name",
        "district_name",
        "province",
    )
    list_editable = (
        "is_active",
    )
    list_per_page = 100
