from datetime import timedelta
from orders.models import Order, StockReservation
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Brand, Category, Product, ProductVariant
from inventory.models import (
    InventoryBatch,
    InventoryDocument,
    InventoryDocumentItem,
    InventoryMovement,
)
from django.test.utils import CaptureQueriesContext
from django.db import connection


class ProductInventoryAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="catalog_inventory_test",
            password="test-password",
        )

        self.brand = Brand.objects.create(
            name="Catalog Test Brand",
            slug="catalog-test-brand",
        )

        self.category = Category.objects.create(
            name="Catalog Test Category",
            slug="catalog-test-category",
        )

        self.product = Product.objects.create(
            name_fa="محصول تست موجودی",
            slug="inventory-test-product",
            brand=self.brand,
            category=self.category,
            description="Inventory API test product",
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            flavor="Test Flavor",
            price=100000,
            stock=999,
        )

    def create_stock(self, variant, quantity, batch_number):
        batch = InventoryBatch.objects.create(
            variant=variant,
            batch_number=batch_number,
            expiration_date=timezone.localdate() + timedelta(days=30),
            created_by=self.user,
        )

        document = InventoryDocument.objects.create(
            document_number=f"CAT-TEST-{batch_number}",
            document_type="inbound",
            created_by=self.user,
        )

        item = InventoryDocumentItem.objects.create(
            document=document,
            variant=variant,
            batch=batch,
            quantity=quantity,
            direction="inbound",
        )

        InventoryMovement.objects.create(
            batch=batch,
            document=document,
            document_item=item,
            movement_type="inbound",
            quantity_delta=quantity,
            created_by=self.user,
        )

        return batch

    def test_product_detail_stock_comes_from_inventory_ledger(self):
        self.create_stock(self.variant, 7, "CAT-BATCH-001")

        response = self.client.get(
            reverse(
                "product-detail",
                kwargs={"slug": self.product.slug},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["variants"][0]["stock"], 7)

    def test_product_detail_stock_excludes_active_reservations(self):
        self.create_stock(self.variant, 7, "CAT-BATCH-002")

        now = timezone.now()

        order = Order.objects.create(
            user=self.user,
            first_name="Test",
            last_name="User",
            mobile="09120000000",
            province="tehran",
            city="Tehran",
            address="Test address",
            subtotal=300000,
            vat_amount=0,
            total_amount=300000,
            status="pending",
            reservation_expires_at=now + timedelta(minutes=10),
        )

        StockReservation.objects.create(
            order=order,
            variant=self.variant,
            quantity=3,
            status="active",
            expires_at=now + timedelta(minutes=5),
        )

        response = self.client.get(
            reverse(
                "product-detail",
                kwargs={"slug": self.product.slug},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["variants"][0]["stock"], 4)

    def test_product_min_price_uses_only_variants_with_available_stock(self):
        ProductVariant.objects.create(
            product=self.product,
            flavor="Cheaper but unavailable",
            price=50000,
            stock=100,
        )

        self.create_stock(self.variant, 5, "CAT-BATCH-003")

        response = self.client.get(reverse("product-list"))

        self.assertEqual(response.status_code, 200)

        product_data = next(
            item for item in response.data["results"] if item["id"] == self.product.id
        )

        self.assertEqual(product_data["min_price"], 100000)

    def test_product_min_price_falls_back_to_active_variants_when_out_of_stock(self):
        ProductVariant.objects.create(
            product=self.product,
            flavor="Cheaper variant",
            price=50000,
            stock=200,
            is_active=True,
        )

        response = self.client.get(reverse("product-list"))

        self.assertEqual(response.status_code, 200)

        product_data = next(
            item for item in response.data["results"] if item["id"] == self.product.id
        )

        self.assertEqual(product_data["min_price"], 50000)

    def test_product_list_query_count_does_not_grow_per_product(self):
        url = reverse("product-list")

        with CaptureQueriesContext(connection) as single_queries:
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

        for index in range(5):
            product = Product.objects.create(
                name_fa=f"Query Test Product {index}",
                slug=f"query-test-product-{index}",
                brand=self.brand,
                category=self.category,
                description="Query optimization test",
            )
            ProductVariant.objects.create(
                product=product,
                flavor=f"Variant {index}",
                price=100000 + index,
                stock=100,
            )

        with CaptureQueriesContext(connection) as multiple_queries:
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 6)

        print(f"\nSingle product queries: {len(single_queries)}")
        print(f"Six products queries: {len(multiple_queries)}")

        self.assertEqual(
            len(single_queries),
            len(multiple_queries),
            "Query count should not grow with the number of products.",
        )


class ProductCatalogMetadataTests(ProductInventoryAPITests):
    def test_product_detail_exposes_scientific_and_authenticity_fields(self):
        self.product.contraindications = "در صورت حساسیت مصرف نشود"
        self.product.medical_advice = "پیش از مصرف با پزشک مشورت شود"
        self.product.license_id = "LICENSE-123"
        self.product.authenticity_code = "AUTH-456"
        self.product.license_details = "اطلاعات تکمیلی"
        self.product.consumption_goals = ["افزایش حجم", "ریکاوری"]
        self.product.save()

        response = self.client.get(
            reverse("product-detail", kwargs={"slug": self.product.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["contraindications"], self.product.contraindications)
        self.assertEqual(response.data["medical_advice"], self.product.medical_advice)
        self.assertEqual(response.data["license_id"], "LICENSE-123")
        self.assertEqual(response.data["authenticity_code"], "AUTH-456")
        self.assertEqual(response.data["consumption_goals"], ["افزایش حجم", "ریکاوری"])

    def test_product_variant_exposes_custom_attributes(self):
        self.variant.attributes = {
            "serving_type": "کپسول",
            "material": "پلی‌استر",
        }
        self.variant.save(update_fields=["attributes"])

        response = self.client.get(
            reverse("product-detail", kwargs={"slug": self.product.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["variants"][0]["attributes"],
            {"serving_type": "کپسول", "material": "پلی‌استر"},
        )

    def test_product_rejects_invalid_consumption_goals(self):
        self.product.consumption_goals = "افزایش حجم"
        with self.assertRaises(Exception):
            self.product.full_clean()

    def test_variant_rejects_invalid_custom_attributes(self):
        self.variant.attributes = ["not", "an", "object"]
        with self.assertRaises(Exception):
            self.variant.full_clean()


class ProductImagePrimaryInvariantTests(ProductInventoryAPITests):
    def test_saving_new_primary_image_unsets_previous_primary(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from catalog.models import ProductImage

        first = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("first.jpg", b"first", content_type="image/jpeg"),
        )
        second = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("second.jpg", b"second", content_type="image/jpeg"),
            is_primary=True,
        )

        first.refresh_from_db()
        self.assertFalse(first.is_primary)
        self.assertTrue(second.is_primary)

    def test_deleting_primary_image_promotes_another_image(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from catalog.models import ProductImage

        first = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("first.jpg", b"first", content_type="image/jpeg"),
        )
        second = ProductImage.objects.create(
            product=self.product,
            image=SimpleUploadedFile("second.jpg", b"second", content_type="image/jpeg"),
        )

        first.delete()
        second.refresh_from_db()
        self.assertTrue(second.is_primary)


class ProductConsumptionGoalFilterTests(ProductInventoryAPITests):
    def test_product_list_can_filter_by_consumption_goal(self):
        self.product.consumption_goals = ["افزایش حجم", "ریکاوری"]
        self.product.save(update_fields=["consumption_goals"])

        other = Product.objects.create(
            name_fa="محصول بدون هدف",
            slug="product-without-goal",
            brand=self.brand,
            category=self.category,
            description="Other product",
        )
        ProductVariant.objects.create(product=other, price=200000, stock=0)

        response = self.client.get(
            reverse("product-list"),
            {"consumption_goal": "ریکاوری"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual([item["id"] for item in response.data["results"]], [self.product.id])

    def test_product_list_ignores_blank_consumption_goal_filter(self):
        response = self.client.get(reverse("product-list"), {"consumption_goal": " "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)

