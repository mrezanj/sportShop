from unittest.mock import MagicMock, patch

from django.test import TestCase

from catalog.models import Brand, Category, Product


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
        queryset.values_list.return_value = [
            product.id for product in self.products
        ]
        mock_filter.return_value = queryset

        response = self.client.get("/api/home/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["bestsellers"]), 4)
        self.assertEqual(len(response.data["new_products"]), 4)
