from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from django.db.models import Sum

from catalog.models import Product, Category, Brand
from catalog.serializers import (
    ProductListSerializer,
    CategorySerializer,
    BrandSerializer,
)
from orders.models import OrderItem
from .models import Testimonial
from .serializers import TestimonialSerializer


@api_view(["GET"])
@permission_classes([AllowAny])
def homepage_data(request):
    """Single endpoint that feeds the entire homepage."""

    # Bestsellers: products with most items sold in paid/completed orders
    bestseller_ids = list(
        OrderItem.objects.filter(
            order__status__in=["paid", "processing", "shipped", "delivered"]
        )
        .values("variant__product")
        .annotate(total_sold=Sum("quantity"))
        .order_by("-total_sold")[:4]
        .values_list("variant__product", flat=True)
    )

    bestsellers_qs = (
        Product.objects.filter(id__in=bestseller_ids, is_active=True)
        .prefetch_related("images", "variants")
        .select_related("brand", "category")
    )

    order_map = {pid: i for i, pid in enumerate(bestseller_ids)}
    bestsellers = sorted(bestsellers_qs, key=lambda p: order_map.get(p.id, 999))

    # Fill up to 4 with newest products (for a brand-new shop or partial sales)
    if len(bestsellers) < 4:
        existing_ids = {p.id for p in bestsellers}
        needed = 4 - len(bestsellers)
        fillers = list(
            Product.objects.filter(is_active=True)
            .exclude(id__in=existing_ids)
            .prefetch_related("images", "variants")
            .select_related("brand", "category")
            .order_by("-created_at")[:needed]
        )
        bestsellers = bestsellers + fillers
        new_products = (
            Product.objects.filter(is_active=True)
            .prefetch_related("images", "variants")
            .select_related("brand", "category")
            .order_by("-created_at")[:4]
        )

    categories = Category.objects.filter(is_active=True, parent__isnull=True).order_by(
        "name"
    )[:8]

    brands = Brand.objects.filter(is_active=True).order_by("name")[:12]

    testimonials = Testimonial.objects.filter(is_active=True).order_by(
        "order", "-created_at"
    )[:8]

    ctx = {"request": request}

    return Response(
        {
            "bestsellers": ProductListSerializer(
                bestsellers, many=True, context=ctx
            ).data,
            "new_products": ProductListSerializer(
                new_products, many=True, context=ctx
            ).data,
            "categories": CategorySerializer(categories, many=True, context=ctx).data,
            "brands": BrandSerializer(brands, many=True, context=ctx).data,
            "testimonials": TestimonialSerializer(
                testimonials, many=True, context=ctx
            ).data,
        }
    )
