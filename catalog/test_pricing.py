from io import BytesIO

from django.contrib.auth.models import Permission, User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.test import override_settings
from openpyxl import Workbook
from rest_framework.test import APITestCase

from catalog.models import (
    Brand,
    Category,
    Product,
    ProductVariant,
    ProductVariantPriceHistory,
)


class ProductPriceManagementAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="price-manager",
            password="test-password",
            is_staff=True,
        )
        permission = Permission.objects.get(
            content_type__app_label="catalog",
            codename="can_manage_product_prices",
        )
        self.user.user_permissions.add(permission)
        self.client.force_authenticate(self.user)

        brand = Brand.objects.create(name="Price Brand", slug="price-brand")
        category = Category.objects.create(name="Price Category", slug="price-category")
        product = Product.objects.create(
            name_fa="محصول قیمت",
            slug="price-product",
            brand=brand,
            category=category,
            description="Product for price management tests",
        )
        self.variant = ProductVariant.objects.create(
            product=product,
            sku="PRICE-SKU-001",
            price=100000,
        )
        self.bulk_url = reverse("product-bulk-price-update")
        self.import_url = reverse("product-import-prices")

    def test_bulk_fixed_price_update_creates_audit_record(self):
        response = self.client.post(
            self.bulk_url,
            {
                "mode": "fixed",
                "items": [{"sku": self.variant.sku, "value": "125000"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.price, 125000)
        history = ProductVariantPriceHistory.objects.get(variant=self.variant)
        self.assertEqual(history.old_price, 100000)
        self.assertEqual(history.new_price, 125000)
        self.assertEqual(history.change_type, "bulk")
        self.assertEqual(history.changed_by, self.user)

    def test_bulk_percentage_update_uses_current_price(self):
        response = self.client.post(
            self.bulk_url,
            {
                "mode": "increase_percent",
                "items": [{"sku": self.variant.sku, "value": "10"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.price, 110000)

    def test_bulk_update_is_atomic_when_any_sku_is_missing(self):
        response = self.client.post(
            self.bulk_url,
            {
                "mode": "fixed",
                "items": [
                    {"sku": self.variant.sku, "value": "125000"},
                    {"sku": "UNKNOWN-SKU", "value": "150000"},
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.price, 100000)
        self.assertFalse(ProductVariantPriceHistory.objects.exists())

    def test_staff_without_price_permission_cannot_change_prices(self):
        self.user.user_permissions.clear()
        response = self.client.post(
            self.bulk_url,
            {
                "mode": "fixed",
                "items": [{"sku": self.variant.sku, "value": "125000"}],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 403)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.price, 100000)

    def test_csv_import_validates_sku_and_records_import_source(self):
        upload = SimpleUploadedFile(
            "prices.csv",
            b"sku,price\nPRICE-SKU-001,135000\n",
            content_type="text/csv",
        )
        response = self.client.post(
            self.import_url,
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.price, 135000)
        self.assertEqual(
            ProductVariantPriceHistory.objects.get(variant=self.variant).change_type,
            "import",
        )

    def test_xlsx_import_updates_price(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["sku", "price"])
        sheet.append([self.variant.sku, 145000])
        buffer = BytesIO()
        workbook.save(buffer)
        upload = SimpleUploadedFile(
            "prices.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response = self.client.post(
            self.import_url,
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.price, 145000)

    def test_price_import_rejects_unknown_sku_without_partial_updates(self):
        upload = SimpleUploadedFile(
            "prices.csv",
            b"sku,price\nPRICE-SKU-001,135000\nUNKNOWN-SKU,150000\n",
            content_type="text/csv",
        )
        response = self.client.post(
            self.import_url,
            {"file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 400)
        self.variant.refresh_from_db()
        self.assertEqual(self.variant.price, 100000)
        self.assertFalse(ProductVariantPriceHistory.objects.exists())
