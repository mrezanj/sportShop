
from django.shortcuts import get_object_or_404

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Province, City


@api_view(["GET"])
@permission_classes([AllowAny])
def list_provinces(request):
    provinces = Province.objects.filter(
        is_active=True,
    ).order_by("name")

    return Response([
        {
            "slug": province.slug,
            "name": province.name,
        }
        for province in provinces
    ])


@api_view(["GET"])
@permission_classes([AllowAny])
def list_cities(request):
    province_slug = request.query_params.get("province", "").strip()

    if not province_slug:
        return Response(
            {"detail": "پارامتر province الزامی است."},
            status=400,
        )

    province = get_object_or_404(
        Province,
        slug=province_slug,
        is_active=True,
    )

    cities = City.objects.filter(
        province=province,
        is_active=True,
    ).order_by("name", "county_name", "district_name", "code")

    return Response([
        {
            "code": city.code,
            "name": city.name,
            "county_name": city.county_name,
            "district_name": city.district_name,
        }
        for city in cities
    ])
