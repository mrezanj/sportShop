from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAdminUser

from .models import Product, ProductImage, ProductVariant
from .management_serializers import (
    CatalogProductImageManagementSerializer,
    CatalogVariantManagementSerializer,
)


class CatalogAssetPermission(IsAdminUser):
    def has_permission(self, request, view):
        return bool(
            super().has_permission(request, view)
            and (
                request.user.is_superuser
                or request.user.has_perm("catalog.can_manage_catalog")
            )
        )


class CatalogProductVariantManagementView(generics.ListCreateAPIView):
    serializer_class = CatalogVariantManagementSerializer
    permission_classes = [CatalogAssetPermission]
    pagination_class = None

    def get_product(self):
        return get_object_or_404(Product, pk=self.kwargs["product_id"])

    def get_queryset(self):
        return ProductVariant.objects.filter(
            product_id=self.kwargs["product_id"]
        ).order_by("id")

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["product"] = self.get_product()
        return context

    def perform_create(self, serializer):
        user = self.request.user
        if not user.is_superuser and not user.has_perm(
            "catalog.can_manage_product_prices"
        ):
            raise PermissionDenied(
                "برای ایجاد SKU همراه با قیمت اولیه، مجوز مدیریت قیمت نیز لازم است."
            )
        serializer.save(product=self.get_product())


class CatalogProductVariantDetailManagementView(generics.RetrieveUpdateAPIView):
    queryset = ProductVariant.objects.select_related("product").all()
    serializer_class = CatalogVariantManagementSerializer
    permission_classes = [CatalogAssetPermission]


class CatalogProductImageManagementView(generics.ListCreateAPIView):
    serializer_class = CatalogProductImageManagementSerializer
    permission_classes = [CatalogAssetPermission]
    pagination_class = None
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_product(self):
        return get_object_or_404(Product, pk=self.kwargs["product_id"])

    def get_queryset(self):
        return ProductImage.objects.filter(
            product_id=self.kwargs["product_id"]
        ).order_by("order", "id")

    def perform_create(self, serializer):
        serializer.save(product=self.get_product())


class CatalogProductImageDetailManagementView(generics.RetrieveUpdateDestroyAPIView):
    queryset = ProductImage.objects.select_related("product").all()
    serializer_class = CatalogProductImageManagementSerializer
    permission_classes = [CatalogAssetPermission]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def perform_update(self, serializer):
        old_image = self.get_object().image
        old_name = old_image.name if old_image else None
        old_storage = old_image.storage if old_image else None
        instance = serializer.save()
        if old_name and instance.image and instance.image.name != old_name:
            transaction.on_commit(lambda: old_storage.delete(old_name))

    def perform_destroy(self, instance):
        image = instance.image
        storage = image.storage if image else None
        name = image.name if image else None
        instance.delete()
        if storage and name:
            transaction.on_commit(lambda: storage.delete(name))
