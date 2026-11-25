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


class ProductVariantIdentityTests(ProductInventoryAPITests):
    def test_servings_and_custom_attributes_distinguish_variants(self):
        base = {
            "product": self.product,
            "flavor": "شکلات",
            "weight": "۱ کیلو",
            "price": 100000,
        }
        servings_variant = ProductVariant.objects.create(
            **base, servings=30, attributes={"form": "پودر"}
        )
        other_servings = ProductVariant.objects.create(
            **base, servings=60, attributes={"form": "پودر"}
        )
        other_attribute = ProductVariant.objects.create(
            **base, servings=30, attributes={"form": "کپسول"}
        )

        self.assertEqual(
            {servings_variant.servings, other_servings.servings, other_attribute.servings},
            {30, 60},
        )
        self.assertEqual(
            len({
                servings_variant.variant_fingerprint,
                other_servings.variant_fingerprint,
                other_attribute.variant_fingerprint,
            }),
            3,
        )

    def test_partial_price_save_does_not_change_identity_fingerprint(self):
        variant = ProductVariant.objects.create(
            product=self.product,
            flavor="توت‌فرنگی",
            servings=30,
            attributes={"form": "پودر"},
            price=100000,
        )
        original_fingerprint = variant.variant_fingerprint
        variant.attributes = {"form": "کپسول"}
        variant.price = 110000
        variant.save(update_fields=["price"])
        variant.refresh_from_db()

        self.assertEqual(variant.attributes, {"form": "پودر"})
        self.assertEqual(variant.variant_fingerprint, original_fingerprint)

    def test_identical_variant_identity_is_rejected(self):
        from django.core.exceptions import ValidationError

        ProductVariant.objects.create(
            product=self.product,
            flavor="وانیل",
            servings=30,
            attributes={"form": "پودر"},
            price=100000,
        )
        duplicate = ProductVariant(
            product=self.product,
            flavor="وانیل",
            servings=30,
            attributes={"form": "پودر"},
            price=120000,
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()


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

class CatalogManagementAPITests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="catalog_manager_test", password="password", is_staff=True
        )
        self.client.force_authenticate(self.staff)

    def test_staff_without_catalog_permission_is_forbidden(self):
        response = self.client.get("/api/management/categories/")
        self.assertEqual(response.status_code, 403)

    def test_catalog_permission_allows_category_and_brand_creation(self):
        from django.contrib.auth.models import Permission
        permission = Permission.objects.get(codename="can_manage_catalog")
        self.staff.user_permissions.add(permission)

        category_response = self.client.post(
            "/api/management/categories/",
            {"name": "Manager Category", "slug": "manager-category", "parent": None, "is_active": True},
            format="json",
        )
        self.assertEqual(category_response.status_code, 201)

        brand_response = self.client.post(
            "/api/management/brands/",
            {"name": "Manager Brand", "slug": "manager-brand", "description": "", "is_active": True},
            format="json",
        )
        self.assertEqual(brand_response.status_code, 201)

    def test_catalog_permission_creates_product_without_stock_or_price_mutation(self):
        from django.contrib.auth.models import Permission
        permission = Permission.objects.get(codename="can_manage_catalog")
        self.staff.user_permissions.add(permission)
        brand = Brand.objects.create(name="Admin Brand", slug="admin-brand")
        category = Category.objects.create(name="Admin Category", slug="admin-category")

        response = self.client.post(
            "/api/management/products/",
            {
                "name_fa": "محصول مدیریتی",
                "name_en": "",
                "slug": "managed-product",
                "brand": brand.slug,
                "category": category.slug,
                "description": "توضیحات",
                "ingredients": "",
                "usage": "",
                "warnings": "",
                "contraindications": "",
                "medical_advice": "",
                "license_id": "",
                "authenticity_code": "",
                "license_details": "",
                "consumption_goals": [],
                "requires_cold_shipping": False,
                "minimum_age": None,
                "is_active": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(ProductVariant.objects.filter(product__slug="managed-product").exists())

    def test_category_cannot_be_moved_under_its_descendant(self):
        from django.contrib.auth.models import Permission
        permission = Permission.objects.get(codename="can_manage_catalog")
        self.staff.user_permissions.add(permission)

        parent = Category.objects.create(name="Parent", slug="cycle-parent")
        child = Category.objects.create(
            name="Child", slug="cycle-child", parent=parent
        )

        response = self.client.patch(
            f"/api/management/categories/{parent.id}/",
            {"parent": child.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        parent.refresh_from_db()
        self.assertIsNone(parent.parent)

    def test_category_cannot_be_its_own_parent(self):
        from django.contrib.auth.models import Permission
        permission = Permission.objects.get(codename="can_manage_catalog")
        self.staff.user_permissions.add(permission)
        category = Category.objects.create(name="Self", slug="self-parent")

        response = self.client.patch(
            f"/api/management/categories/{category.id}/",
            {"parent": category.id},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        category.refresh_from_db()
        self.assertIsNone(category.parent)

    def test_category_and_brand_detail_endpoints_do_not_allow_delete(self):
        from django.contrib.auth.models import Permission
        permission = Permission.objects.get(codename="can_manage_catalog")
        self.staff.user_permissions.add(permission)
        category = Category.objects.create(name="Protected Category", slug="protected-category")
        brand = Brand.objects.create(name="Protected Brand", slug="protected-brand")
        category_response = self.client.delete(f"/api/management/categories/{category.id}/")
        brand_response = self.client.delete(f"/api/management/brands/{brand.id}/")
        self.assertEqual(category_response.status_code, 405)
        self.assertEqual(brand_response.status_code, 405)
        self.assertTrue(Category.objects.filter(pk=category.pk).exists())
        self.assertTrue(Brand.objects.filter(pk=brand.pk).exists())


class CatalogVariantAndGalleryManagementAPITests(TestCase):
    def setUp(self):
        from rest_framework.test import APIClient
        from django.contrib.auth.models import Permission

        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="catalog_assets_manager", password="password", is_staff=True
        )
        self.client.force_authenticate(self.staff)
        self.brand = Brand.objects.create(name="Asset Brand", slug="asset-brand")
        self.category = Category.objects.create(name="Asset Category", slug="asset-category")
        self.product = Product.objects.create(
            name_fa="محصول مدیریت تنوع",
            slug="asset-product",
            brand=self.brand,
            category=self.category,
            description="تست مدیریت تنوع و تصویر",
        )
        self.catalog_permission = Permission.objects.get(codename="can_manage_catalog")
        self.price_permission = Permission.objects.get(codename="can_manage_product_prices")
        self.staff.user_permissions.add(self.catalog_permission)

    def grant_price_permission(self):
        self.staff.user_permissions.add(self.price_permission)

    def test_staff_without_catalog_permission_cannot_access_variants_or_images(self):
        self.staff.user_permissions.remove(self.catalog_permission)
        variants = self.client.get(f"/api/management/products/{self.product.id}/variants/")
        images = self.client.get(f"/api/management/products/{self.product.id}/images/")
        self.assertEqual(variants.status_code, 403)
        self.assertEqual(images.status_code, 403)

    def test_variant_creation_requires_price_permission_and_records_initial_price(self):
        payload = {
            "flavor": "شکلات",
            "weight": "۱ کیلو",
            "servings": ۳۰,
            "attributes": {"form": "پودر"},
            "initial_price": "125000",
        }
        denied = self.client.post(
            f"/api/management/products/{self.product.id}/variants/",
            payload,
            format="json",
        )
        self.assertEqual(denied.status_code, 403)
        self.assertFalse(ProductVariant.objects.filter(product=self.product).exists())

        self.grant_price_permission()
        response = self.client.post(
            f"/api/management/products/{self.product.id}/variants/",
            payload,
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        variant = ProductVariant.objects.get(product=self.product)
        self.assertEqual(variant.price, 125000)
        self.assertTrue(variant.sku)
        history = ProductVariantPriceHistory.objects.get(variant=variant)
        self.assertEqual(history.change_type, "initial")
        self.assertIsNone(history.old_price)
        self.assertEqual(history.new_price, 125000)

    def test_variant_update_cannot_change_price_stock_or_sku(self):
        variant = ProductVariant.objects.create(
            product=self.product, flavor="وانیل", price=100000, stock=17
        )
        response = self.client.patch(
            f"/api/management/variants/{variant.id}/",
            {"flavor": "توت‌فرنگی", "price": "1", "stock": 0, "sku": "HACKED"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        variant.refresh_from_db()
        self.assertEqual(variant.flavor, "توت‌فرنگی")
        self.assertEqual(variant.price, 100000)
        self.assertEqual(variant.stock, 17)
        self.assertNotEqual(variant.sku, "HACKED")

    def test_duplicate_variant_fingerprint_is_rejected_by_management_api(self):
        ProductVariant.objects.create(
            product=self.product, flavor="وانیل", servings=30,
            attributes={"form": "پودر"}, price=100000,
        )
        self.grant_price_permission()
        response = self.client.post(
            f"/api/management/products/{self.product.id}/variants/",
            {
                "flavor": "وانیل",
                "servings": 30,
                "attributes": {"form": "پودر"},
                "initial_price": "110000",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_image_upload_primary_selection_and_delete_promotes_remaining_image(self):
        import base64
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import ProductImage

        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p0sAAAAASUVORK5CYII="
        )
        first = self.client.post(
            f"/api/management/products/{self.product.id}/images/",
            {"image": SimpleUploadedFile("first.png", png, content_type="image/png"), "alt_text": "اول", "order": 1},
            format="multipart",
        )
        self.assertEqual(first.status_code, 201, first.data)
        second = self.client.post(
            f"/api/management/products/{self.product.id}/images/",
            {"image": SimpleUploadedFile("second.png", png, content_type="image/png"), "alt_text": "دوم", "order": 2, "is_primary": True},
            format="multipart",
        )
        self.assertEqual(second.status_code, 201, second.data)
        first_image = ProductImage.objects.get(pk=first.data["id"])
        second_image = ProductImage.objects.get(pk=second.data["id"])
        first_image.refresh_from_db()
        self.assertFalse(first_image.is_primary)
        self.assertTrue(second_image.is_primary)

        deleted = self.client.delete(f"/api/management/images/{second_image.id}/")
        self.assertEqual(deleted.status_code, 204)
        first_image.refresh_from_db()
        self.assertTrue(first_image.is_primary)
