
from django.db.models import CharField
from django.db.models.functions import Cast
from rest_framework import viewsets
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from .models import Category, Brand, Product
from .serializers import (
    CategorySerializer,
    BrandSerializer,
    ProductListSerializer,
    ProductDetailSerializer,
)
from .services import build_product_inventory_context


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    lookup_field = "slug"


class BrandViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Brand.objects.filter(is_active=True)
    serializer_class = BrandSerializer
    lookup_field = "slug"
    filter_backends = [SearchFilter]
    search_fields = ["name"]


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.filter(is_active=True).select_related(
        "brand", "category"
    ).prefetch_related("images", "variants")

    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["brand__slug", "category__slug"]
    search_fields = ["name_fa", "name_en", "brand__name"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        queryset = super().get_queryset()
        goal = self.request.query_params.get("consumption_goal", "").strip()
        if goal:
            queryset = queryset.annotate(\n                consumption_goals_text=Cast("consumption_goals", output_field=CharField())\n            ).filter(consumption_goals_text__icontains=goal)
        return queryset

    def get_serializer_class(self):
        if self.action == "retrieve":
            return ProductDetailSerializer
        return ProductListSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)
        products = page if page is not None else queryset

        context = self.get_serializer_context()
        context.update(build_product_inventory_context(products))

        serializer = self.get_serializer(
            products,
            many=True,
            context=context,
        )

        if page is not None:
            return self.get_paginated_response(serializer.data)

        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        product = self.get_object()

        context = self.get_serializer_context()
        context.update(build_product_inventory_context([product]))

        serializer = self.get_serializer(
            product,
            context=context,
        )

        return Response(serializer.data)
