from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CategoryViewSet, BrandViewSet, ProductViewSet
from .discount_api import DiscountCampaignViewSet
from .management_views import (CatalogProductVariantManagementView, CatalogProductVariantDetailManagementView, CatalogProductImageManagementView, CatalogProductImageDetailManagementView)
from .views import (CatalogCategoryManagementView, CatalogCategoryDetailManagementView, CatalogBrandManagementView, CatalogBrandDetailManagementView, CatalogProductManagementView, CatalogProductDetailManagementView)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'brands', BrandViewSet, basename='brand')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'discounts', DiscountCampaignViewSet, basename='discount')

urlpatterns = [
    path('management/categories/', CatalogCategoryManagementView.as_view(), name='catalog-management-categories'),
    path('management/categories/<int:pk>/', CatalogCategoryDetailManagementView.as_view(), name='catalog-management-category-detail'),
    path('management/brands/', CatalogBrandManagementView.as_view(), name='catalog-management-brands'),
    path('management/brands/<int:pk>/', CatalogBrandDetailManagementView.as_view(), name='catalog-management-brand-detail'),
    path('management/products/', CatalogProductManagementView.as_view(), name='catalog-management-products'),
    path('management/products/<int:pk>/', CatalogProductDetailManagementView.as_view(), name='catalog-management-product-detail'),
    path('management/products/<int:product_id>/variants/', CatalogProductVariantManagementView.as_view(), name='catalog-management-product-variants'),
    path('management/variants/<int:pk>/', CatalogProductVariantDetailManagementView.as_view(), name='catalog-management-variant-detail'),
    path('management/products/<int:product_id>/images/', CatalogProductImageManagementView.as_view(), name='catalog-management-product-images'),
    path('management/images/<int:pk>/', CatalogProductImageDetailManagementView.as_view(), name='catalog-management-image-detail'),
    path('', include(router.urls)),
]