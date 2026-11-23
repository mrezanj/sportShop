
from locations.models import City, Province


def get_test_tehran_city():
    province, _ = Province.objects.get_or_create(
        slug="tehran",
        defaults={
            "name": "تهران",
            "source_code": "TEST-TEH",
            "is_active": True,
        },
    )

    if not province.is_active:
        province.is_active = True
        province.save(update_fields=["is_active"])

    city, _ = City.objects.get_or_create(
        code="TSTTEH001",
        defaults={
            "province": province,
            "name": "تهران",
            "county_name": "تهران",
            "district_name": "مرکزی",
            "is_active": True,
        },
    )

    if (
        city.province_id != province.id
        or not city.is_active
    ):
        city.province = province
        city.is_active = True
        city.save(update_fields=["province", "is_active"])

    return city
