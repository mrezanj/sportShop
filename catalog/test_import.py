from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .models import Brand, Category, Product, ProductVariant, ProductVariantPriceHistory


class CatalogImportAPITests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="catalog-import-admin",
            password="test-password",
            is_staff=True,
        )
        permission = Permission.objects.get(
            content_type__app_label="catalog",
            codename="can_manage_product_prices",
        )
        self.user.user_permissions.add(permission)
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.brand = Brand.objects.create(name="Import Brand", slug="import-brand")
        self.category = Category.objects.create(
            name="Import Category", slug="import-category"
        )

    def upload(self, content, filename="catalog.csv"):
        return SimpleUploadedFile(
            filename,
            content.encode("utf-8"),
            content_type="text/csv",
        )

    def test_import_creates_product_variant_and_price_history(self):
        content = (
            "product_slug,name_fa,brand_slug,category_slug,description,price,sku,"
            "flavor,weight,consumption_goals\n"
            "imported-whey,پروتئین وی,import-brand,import-category,توضیحات,125000,"
            "WHEY-001,شکلات,۲ کیلو,[\"ریکاوری\"]\n"
        )
        response = self.client.post(
            reverse("product-import-catalog"),
            {"file": self.upload(content)},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["products_created"], 1)
        self.assertEqual(response.data["variants_created"], 1)
        product = Product.objects.get(slug="imported-whey")
        variant = ProductVariant.objects.get(sku="WHEY-001")
        self.assertEqual(variant.product_id, product.id)
        self.assertEqual(variant.price, 125000)
        self.assertEqual(variant.stock, 0)
        self.assertEqual(product.consumption_goals, ["ریکاوری"])
        self.assertEqual(
            ProductVariantPriceHistory.objects.filter(
                variant=variant, change_type="import"
            ).count(),
            1,
        )

    def test_import_updates_existing_variant_and_records_price_history(self):
        product = Product.objects.create(
            name_fa="محصول قبلی",
            slug="existing-product",
            brand=self.brand,
            category=self.category,
            description="توضیح قبلی",
        )
        variant = ProductVariant.objects.create(
            product=product, sku="EXIST-001", price=100000
        )
        content = (
            "product_slug,name_fa,brand_slug,category_slug,description,price,sku\n"
            "existing-product,نام جدید,import-brand,import-category,توضیح جدید,150000,EXIST-001\n"
        )
        response = self.client.post(
            reverse("product-import-catalog"),
            {"file": self.upload(content)},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200, response.data)
        product.refresh_from_db()
        variant.refresh_from_db()
        self.assertEqual(product.name_fa, "نام جدید")
        self.assertEqual(variant.price, 150000)
        self.assertEqual(variant.stock, 0)
        history = ProductVariantPriceHistory.objects.filter(variant=variant).latest("id")
        self.assertEqual(history.old_price, 100000)
        self.assertEqual(history.new_price, 150000)

    def test_import_is_atomic_when_a_later_row_is_invalid(self):
        content = (
            "product_slug,name_fa,brand_slug,category_slug,description,price,sku\n"
            "valid-first,محصول اول,import-brand,import-category,توضیح,100000,VALID-001\n"
            "invalid-second,محصول دوم,missing-brand,import-category,توضیح,200000,INVALID-002\n"
        )
        response = self.client.post(
            reverse("product-import-catalog"),
            {"file": self.upload(content)},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Product.objects.filter(slug="valid-first").exists())
        self.assertFalse(ProductVariant.objects.filter(sku="VALID-001").exists())

    def test_import_rejects_stock_column_to_protect_inventory_ledger(self):
        content = (
            "product_slug,name_fa,brand_slug,category_slug,description,price,stock\n"
            "stock-product,محصول,import-brand,import-category,توضیح,100000,50\n"
        )
        response = self.client.post(
            reverse("product-import-catalog"),
            {"file": self.upload(content)},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("موجودی", str(response.data))


    def test_import_rejects_more_than_5000_rows_during_file_read(self):
        header = "product_slug,name_fa,brand_slug,category_slug,description,price,sku\n"
        row = "too-many,محصول,import-brand,import-category,توضیح,100000,TOO-MANY\n"
        response = self.client.post(
            reverse("product-import-catalog"),
            {"file": self.upload(header + row * 5001)},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("۵۰۰۰", str(response.data))
        self.assertFalse(Product.objects.filter(slug="too-many").exists())

    def test_import_distinguishes_variants_by_servings_and_custom_attributes(self):
        content = (
            "product_slug,name_fa,brand_slug,category_slug,description,price,sku,flavor,weight,servings,attributes\n"
            "multi-variant,محصول,import-brand,import-category,توضیح,100000,VAR-30,شکلات,۱ کیلو,30,{}\n"
            "multi-variant,محصول,import-brand,import-category,توضیح,110000,VAR-60,شکلات,۱ کیلو,60,{}\n"
            "multi-variant,محصول,import-brand,import-category,توضیح,120000,VAR-CAPS,شکلات,۱ کیلو,30,""{""form"":""کپسول""}""\n"
        )
        response = self.client.post(
            reverse("product-import-catalog"),
            {"file": self.upload(content)},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["variants_created"], 3)
        variants = ProductVariant.objects.filter(product__slug="multi-variant")
        self.assertEqual(variants.count(), 3)
        self.assertEqual(set(variants.values_list("servings", flat=True)), {30, 60})

    def test_import_requires_price_management_permission(self):
        self.user.user_permissions.clear()
        response = self.client.post(
            reverse("product-import-catalog"),
            {"file": self.upload("product_slug,name_fa,brand_slug,category_slug,description,price\nx,x,x,x,x,1")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 403)
