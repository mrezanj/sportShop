from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from catalog.models import Brand, Category, Product, ProductVariant
from inventory.models import (
    InventoryBatch,
    InventoryDocument,
    InventoryDocumentItem,
    InventoryMovement,
)


class HomepageDataTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(
            name="Test Brand",
            slug="test-brand",
        )
        self.category = Category.objects.create(
            name="Test Category",
            slug="test-category",
        )

        self.products = [
            Product.objects.create(
                name_fa=f"محصول آزمایشی {i}",
                slug=f"test-product-{i}",
                brand=self.brand,
                category=self.category,
                description="Test description",
            )
            for i in range(4)
        ]

    @patch("core.views.OrderItem.objects.filter")
    def test_homepage_returns_new_products_when_four_bestsellers_exist(
        self, mock_filter
    ):
        queryset = MagicMock()
        queryset.values.return_value = queryset
        queryset.annotate.return_value = queryset
        queryset.order_by.return_value = queryset
        queryset.values_list.return_value = [product.id for product in self.products]
        mock_filter.return_value = queryset

        response = self.client.get("/api/home/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["bestsellers"]), 4)
        self.assertEqual(len(response.data["new_products"]), 4)

    @patch("core.views.OrderItem.objects.filter")
    def test_homepage_min_price_uses_inventory_ledger(self, mock_filter):
        queryset = MagicMock()
        queryset.values.return_value = queryset
        queryset.annotate.return_value = queryset
        queryset.order_by.return_value = queryset
        queryset.values_list.return_value = [product.id for product in self.products]
        mock_filter.return_value = queryset

        product = self.products[0]

        available_variant = ProductVariant.objects.create(
            product=product,
            flavor="Available variant",
            price=100000,
            stock=0,
        )

        unavailable_variant = ProductVariant.objects.create(
            product=product,
            flavor="Unavailable variant",
            price=50000,
            stock=999,
        )

        user = User.objects.create_user(
            username="homepage_inventory_test",
            password="test-password",
        )

        batch = InventoryBatch.objects.create(
            variant=available_variant,
            batch_number="HOME-BATCH-001",
            expiration_date=timezone.localdate() + timedelta(days=30),
            created_by=user,
        )

        document = InventoryDocument.objects.create(
            document_number="HOME-DOC-001",
            document_type="inbound",
            created_by=user,
        )

        item = InventoryDocumentItem.objects.create(
            document=document,
            variant=available_variant,
            batch=batch,
            quantity=6,
            direction="inbound",
        )

        InventoryMovement.objects.create(
            batch=batch,
            document=document,
            document_item=item,
            movement_type="inbound",
            quantity_delta=6,
            created_by=user,
        )

        response = self.client.get("/api/home/")

        self.assertEqual(response.status_code, 200)

        bestseller = next(
            item for item in response.data["bestsellers"] if item["id"] == product.id
        )

        new_product = next(
            item for item in response.data["new_products"] if item["id"] == product.id
        )

        self.assertEqual(bestseller["min_price"], 100000)
        self.assertEqual(new_product["min_price"], 100000)
