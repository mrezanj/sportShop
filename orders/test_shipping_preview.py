
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from inventory.models import (
    InventoryBatch,
    InventoryDocument,
    InventoryDocumentItem,
    InventoryMovement,
)
from locations.testing import get_test_tehran_city
from orders.models import Order, StockReservation
from catalog.models import DiscountCampaign

from .test_shipping import ShippingTestDataMixin


class ShippingPreviewAPITests(
    ShippingTestDataMixin,
    APITestCase,
):
    def setUp(self):
        self.user = User.objects.create_user(
            username="shipping-preview-test",
            password="test-password",
        )
        self.client.force_authenticate(user=self.user)

        self.city = get_test_tehran_city()

        self.method = self.create_shipping_method()

        self.rate = self.create_shipping_rate(
            self.method,
            cost=50000,
            included_weight=5000,
            additional_cost=10000,
        )

        self.variant = self.create_product_variant(
            weight=1000,
            special_packaging=True,
            packaging_cost=7000,
        )

        self.create_inventory_stock(
            variant=self.variant,
            quantity=10,
        )

        self.url = reverse("shipping-preview")

    def create_inventory_stock(self, variant, quantity):
        batch = InventoryBatch.objects.create(
            variant=variant,
            batch_number=f"PREVIEW-{variant.id}",
            expiration_date=timezone.localdate() + timedelta(days=30),
            created_by=self.user,
        )

        document = InventoryDocument.objects.create(
            document_number=f"PREVIEW-DOC-{variant.id}",
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

    def payload(self, **overrides):
        data = {
            "items": [
                {
                    "variant_id": self.variant.id,
                    "quantity": 2,
                }
            ],
            "shipping_method_slug": self.method.slug,
            "province": self.city.province.slug,
            "city_code": self.city.code,
        }
        data.update(overrides)
        return data

    def test_authenticated_user_can_preview_shipping_costs(self):
        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertTrue(response.data["quote_token"])
        self.assertEqual(response.data["quote_expires_in"], 600)
        self.assertEqual(response.data["items"][0]["variant_id"], self.variant.id)
        self.assertEqual(response.data["items"][0]["unit_price"], 100000)
        self.assertEqual(response.data["items"][0]["line_subtotal"], 200000)

        self.assertEqual(response.data["subtotal"], 200000)
        self.assertEqual(response.data["vat_amount"], 20000)
        self.assertEqual(response.data["shipping_cost"], 50000)
        self.assertEqual(response.data["packaging_cost"], 14000)
        self.assertEqual(response.data["total_amount"], 284000)

        self.assertEqual(
            response.data["shipping"]["base_cost"],
            50000,
        )
        self.assertEqual(
            response.data["shipping"]["additional_weight_cost"],
            0,
        )
        self.assertFalse(response.data["shipping"]["is_free"])

        self.assertEqual(
            response.data["packaging"]["raw_cost"],
            14000,
        )
        self.assertFalse(response.data["packaging"]["is_free"])

    def test_preview_applies_coupon_and_recalculates_tax_and_total(self):
        now = timezone.now()
        DiscountCampaign.objects.create(
            name="Preview coupon",
            code="PREVIEW10",
            scope="product",
            product=self.variant.product,
            discount_type="percent",
            value=Decimal("10"),
            starts_at=now - timedelta(days=1),
            ends_at=now + timedelta(days=1),
        )

        response = self.client.post(
            self.url,
            self.payload(discount_code="preview10"),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["subtotal"], 200000)
        self.assertEqual(response.data["discount_amount"], 20000)
        self.assertEqual(response.data["discounted_subtotal"], 180000)
        self.assertEqual(response.data["vat_amount"], 18000)
        self.assertEqual(response.data["total_amount"], 262000)
        self.assertEqual(response.data["discounts"][0]["code"], "PREVIEW10")
        self.assertEqual(response.data["items"][0]["line_subtotal"], 180000)

    def test_preview_rejects_unknown_discount_code(self):
        response = self.client.post(
            self.url,
            self.payload(discount_code="NOT-A-REAL-CODE"),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("discount_code", response.data)

    def test_preview_does_not_create_order_or_stock_reservation(self):
        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(StockReservation.objects.count(), 0)

    def test_duplicate_variant_items_are_aggregated(self):
        response = self.client.post(
            self.url,
            self.payload(
                items=[
                    {
                        "variant_id": self.variant.id,
                        "quantity": 1,
                    },
                    {
                        "variant_id": self.variant.id,
                        "quantity": 2,
                    },
                ]
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["subtotal"], 300000)
        self.assertEqual(response.data["packaging_cost"], 21000)

    def test_insufficient_inventory_is_rejected(self):
        response = self.client.post(
            self.url,
            self.payload(
                items=[
                    {
                        "variant_id": self.variant.id,
                        "quantity": 11,
                    }
                ]
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("items", response.data)

    def test_unauthenticated_user_cannot_preview(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 401)

    def test_empty_items_are_rejected(self):
        response = self.client.post(
            self.url,
            self.payload(items=[]),
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_unknown_variant_is_rejected(self):
        response = self.client.post(
            self.url,
            self.payload(
                items=[
                    {
                        "variant_id": 99999999,
                        "quantity": 1,
                    }
                ]
            ),
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_city_is_rejected(self):
        response = self.client.post(
            self.url,
            self.payload(city_code="INVALID-CITY"),
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_method_restricted_to_another_city_is_rejected(self):
        from locations.models import City

        other_city = City.objects.create(
            province=self.city.province,
            code="TSTPREV002",
            name="شهر آزمایشی دیگر",
            county_name="تهران",
            district_name="مرکزی",
            is_active=True,
        )

        self.method.restricted_province = self.city.province.slug
        self.method.restricted_city = other_city
        self.method.save()

        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_inactive_variant_is_rejected(self):
        self.variant.is_active = False
        self.variant.save(update_fields=["is_active"])

        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_inactive_shipping_method_is_rejected(self):
        self.method.is_active = False
        self.method.save(update_fields=["is_active"])

        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_free_shipping_and_packaging_thresholds_are_applied(self):
        from orders.models import ShippingConfiguration

        configuration = ShippingConfiguration.objects.get_or_create(
            singleton_key=1,
        )[0]

        configuration.free_shipping_threshold = Decimal("200000")
        configuration.free_packaging_threshold = Decimal("200000")
        configuration.save()

        response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["shipping_cost"], 0)
        self.assertEqual(response.data["packaging_cost"], 0)
        self.assertTrue(response.data["shipping"]["is_free"])
        self.assertTrue(response.data["packaging"]["is_free"])

    def test_preview_quote_creates_order_once_with_matching_shipping_snapshot(self):
        preview_response = self.client.post(
            self.url,
            self.payload(),
            format="json",
        )
        self.assertEqual(preview_response.status_code, 200)

        order_payload = {
            **self.payload(),
            "quote_token": preview_response.data["quote_token"],
            "first_name": "آزمایش",
            "last_name": "کاربر",
            "mobile": "09123456789",
            "address": "آدرس کامل آزمایشی برای ثبت سفارش",
            "postal_code": "1234567890",
            "notes": "",
        }
        create_url = reverse("create-order")

        create_response = self.client.post(
            create_url,
            order_payload,
            format="json",
        )

        self.assertEqual(create_response.status_code, 201)
        order = Order.objects.get(order_number=create_response.data["order_number"])
        self.assertEqual(
            order.total_amount,
            Decimal(str(preview_response.data["total_amount"])),
        )
        self.assertEqual(
            order.shipping_cost,
            Decimal(str(preview_response.data["shipping_cost"])),
        )
        self.assertEqual(
            order.packaging_cost,
            Decimal(str(preview_response.data["packaging_cost"])),
        )
        self.assertEqual(
            order.shipping_calculation_snapshot["rate_id"],
            self.rate.id,
        )
        self.assertEqual(
            order.shipping_calculation_snapshot["city_code"],
            self.city.code,
        )
        reservation = StockReservation.objects.get(order=order)
        self.assertEqual(reservation.quantity, 2)
        self.assertEqual(reservation.status, "active")

        replay_response = self.client.post(
            create_url,
            order_payload,
            format="json",
        )
        self.assertEqual(replay_response.status_code, 400)
        self.assertEqual(Order.objects.count(), 1)
