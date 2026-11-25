from decimal import Decimal
from uuid import uuid4

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APITestCase

from catalog.models import Brand, Category, Product, ProductVariant
from locations.models import City, Province
from locations.testing import get_test_tehran_city
from orders.models import (
    ShippingConfiguration,
    ShippingMethod,
    ShippingRate,
)
from orders.shipping import (
    ShippingCalculationError,
    calculate_shipping,
)


class ShippingTestDataMixin:
    def create_product_variant(
        self,
        *,
        weight=1000,
        length=None,
        width=None,
        height=None,
        cold=False,
        special_packaging=False,
        packaging_cost=0,
    ):
        unique_suffix = uuid4().hex[:12]

        brand = Brand.objects.create(
            name=f"Shipping Test Brand {unique_suffix}",
            slug=f"shipping-test-brand-{unique_suffix}",
        )
        category = Category.objects.create(
            name=f"Shipping Test Category {unique_suffix}",
            slug=f"shipping-test-category-{unique_suffix}",
        )
        product = Product.objects.create(
            name_fa=f"محصول آزمایش ارسال {unique_suffix}",
            slug=f"shipping-test-product-{unique_suffix}",
            brand=brand,
            category=category,
            description="محصول آزمایشی",
            requires_cold_shipping=cold,
        )

        variant = ProductVariant.objects.create(
            product=product,
            price=Decimal("100000"),
            stock=10,
            shipping_weight_grams=weight,
            shipping_length_cm=length,
            shipping_width_cm=width,
            shipping_height_cm=height,
            requires_special_packaging=special_packaging,
            special_packaging_cost=Decimal(str(packaging_cost)),
        )

        return variant

    def create_shipping_method(self, **kwargs):
        defaults = {
            "name": "ارسال آزمایشی",
            "slug": "shipping-test-method",
            "is_active": True,
        }
        defaults.update(kwargs)
        return ShippingMethod.objects.create(**defaults)

    def create_shipping_rate(
        self,
        method,
        *,
        city=None,
        province="tehran",
        cost=50000,
        included_weight=1000,
        weight_step=1000,
        additional_cost=10000,
        cold_cost=15000,
        is_active=True,
    ):
        return ShippingRate.objects.create(
            method=method,
            province=province,
            city=city,
            cost=Decimal(str(cost)),
            included_weight_grams=included_weight,
            additional_weight_step_grams=weight_step,
            additional_weight_cost=Decimal(str(additional_cost)),
            cold_shipping_cost=Decimal(str(cold_cost)),
            is_active=is_active,
        )

    def calculate(self, method, city, variant, quantity=1, subtotal=100000):
        return calculate_shipping(
            method=method,
            province=city.province.slug,
            city=city,
            subtotal=Decimal(str(subtotal)),
            items=[
                {
                    "variant": variant,
                    "quantity": quantity,
                }
            ],
        )


class ShippingCalculationTests(
    ShippingTestDataMixin,
    TestCase,
):
    def setUp(self):
        self.city = get_test_tehran_city()

        self.method = self.create_shipping_method()

        self.rate = self.create_shipping_rate(
            self.method,
        )

        self.variant = self.create_product_variant()

    def test_city_rate_has_priority_over_province_rate(self):
        province_rate = self.rate

        city_rate = self.create_shipping_rate(
            self.method,
            city=self.city,
            cost=20000,
        )

        result = self.calculate(
            self.method,
            self.city,
            self.variant,
        )

        self.assertEqual(result["rate"].id, city_rate.id)
        self.assertNotEqual(result["rate"].id, province_rate.id)
        self.assertEqual(result["shipping_cost"], Decimal("20000"))
        self.assertEqual(
            result["snapshot"]["rate_id"],
            city_rate.id,
        )

    def test_inactive_city_rate_blocks_province_fallback(self):
        self.create_shipping_rate(
            self.method,
            city=self.city,
            cost=20000,
            is_active=False,
        )

        with self.assertRaises(ShippingCalculationError):
            self.calculate(
                self.method,
                self.city,
                self.variant,
            )

    def test_province_rate_is_used_when_city_rate_does_not_exist(self):
        result = self.calculate(
            self.method,
            self.city,
            self.variant,
        )

        self.assertEqual(result["rate"].id, self.rate.id)
        self.assertEqual(result["shipping_cost"], Decimal("50000"))

    def test_missing_province_and_city_rates_are_rejected(self):
        self.rate.delete()

        with self.assertRaises(ShippingCalculationError):
            self.calculate(
                self.method,
                self.city,
                self.variant,
            )

    def test_inactive_province_rate_is_rejected(self):
        self.rate.is_active = False
        self.rate.save(update_fields=["is_active"])

        with self.assertRaises(ShippingCalculationError):
            self.calculate(
                self.method,
                self.city,
                self.variant,
            )

    def test_shipping_method_restricted_to_another_city_is_rejected(self):
        other_city = City.objects.create(
            province=self.city.province,
            code="TSTTEH002",
            name="شهر آزمایشی دیگر",
            county_name="تهران",
            district_name="مرکزی",
            is_active=True,
        )

        self.method.restricted_city = self.city
        self.method.restricted_province = "tehran"
        self.method.save()

        with self.assertRaises(ShippingCalculationError):
            self.calculate(
                self.method,
                other_city,
                self.variant,
            )

    def test_inactive_city_is_rejected(self):
        self.city.is_active = False
        self.city.save(update_fields=["is_active"])

        with self.assertRaises(ShippingCalculationError):
            self.calculate(
                self.method,
                self.city,
                self.variant,
            )

    def test_city_from_another_province_is_rejected(self):
        other_province = Province.objects.create(
            slug="test-province",
            name="استان آزمایشی",
            source_code="TEST-PROV",
            is_active=True,
        )

        other_city = City.objects.create(
            province=other_province,
            code="TSTOTH001",
            name="شهر آزمایشی",
            county_name="شهرستان آزمایشی",
            district_name="مرکزی",
            is_active=True,
        )

        with self.assertRaises(ShippingCalculationError):
            calculate_shipping(
                method=self.method,
                province="tehran",
                city=other_city,
                subtotal=Decimal("100000"),
                items=[
                    {
                        "variant": self.variant,
                        "quantity": 1,
                    }
                ],
            )

    def test_inactive_shipping_method_is_rejected(self):
        self.method.is_active = False
        self.method.save(update_fields=["is_active"])

        with self.assertRaises(ShippingCalculationError):
            self.calculate(
                self.method,
                self.city,
                self.variant,
            )

    def test_volumetric_weight_and_additional_weight_cost(self):
        variant = self.create_product_variant(
            weight=1000,
            length=200,
            width=200,
            height=200,
        )

        self.rate.included_weight_grams = 1000
        self.rate.additional_weight_step_grams = 500
        self.rate.additional_weight_cost = Decimal("10000")
        self.rate.save(
            update_fields=[
                "included_weight_grams",
                "additional_weight_step_grams",
                "additional_weight_cost",
            ]
        )

        result = self.calculate(
            self.method,
            self.city,
            variant,
        )

        self.assertEqual(
            result["shipping_actual_weight_grams"],
            1000,
        )
        self.assertEqual(
            result["shipping_volumetric_weight_grams"],
            1600,
        )
        self.assertEqual(
            result["shipping_billable_weight_grams"],
            1600,
        )
        self.assertEqual(
            result["snapshot"]["additional_weight_steps"],
            2,
        )
        self.assertEqual(
            result["shipping_cost"],
            Decimal("70000"),
        )

    def test_cold_shipping_cost_is_added_once_per_order(self):
        self.rate.included_weight_grams = 5000
        self.rate.save(update_fields=["included_weight_grams"])

        variant = self.create_product_variant(
            cold=True,
        )

        result = self.calculate(
            self.method,
            self.city,
            variant,
            quantity=3,
        )

        self.assertTrue(result["snapshot"]["requires_cold_shipping"])
        self.assertEqual(
            result["snapshot"]["cold_shipping_cost"],
            "15000",
        )
        self.assertEqual(
            result["shipping_cost"],
            Decimal("65000"),
        )

    def test_special_packaging_cost_is_calculated_per_unit(self):
        variant = self.create_product_variant(
            special_packaging=True,
            packaging_cost=7000,
        )

        result = self.calculate(
            self.method,
            self.city,
            variant,
            quantity=3,
        )

        self.assertEqual(
            result["packaging_cost"],
            Decimal("21000"),
        )
        self.assertFalse(result["packaging_is_free"])
        self.assertEqual(
            result["snapshot"]["raw_packaging_cost"],
            "21000",
        )

    def test_free_shipping_and_packaging_thresholds_are_independent(self):
        configuration = ShippingConfiguration.objects.get_or_create(
            singleton_key=1,
        )[0]

        configuration.free_shipping_threshold = Decimal("200000")
        configuration.free_packaging_threshold = Decimal("300000")
        configuration.save()

        variant = self.create_product_variant(
            special_packaging=True,
            packaging_cost=7000,
        )

        result = self.calculate(
            self.method,
            self.city,
            variant,
            subtotal=250000,
        )

        self.assertTrue(result["shipping_is_free"])
        self.assertEqual(
            result["shipping_cost"],
            Decimal("0"),
        )
        self.assertFalse(result["packaging_is_free"])
        self.assertEqual(
            result["packaging_cost"],
            Decimal("7000"),
        )

    def test_free_packaging_does_not_automatically_make_shipping_free(self):
        configuration = ShippingConfiguration.objects.get_or_create(
            singleton_key=1,
        )[0]

        configuration.free_shipping_threshold = Decimal("4000000")
        configuration.free_packaging_threshold = Decimal("200000")
        configuration.save()

        variant = self.create_product_variant(
            special_packaging=True,
            packaging_cost=7000,
        )

        result = self.calculate(
            self.method,
            self.city,
            variant,
            subtotal=250000,
        )

        self.assertFalse(result["shipping_is_free"])
        self.assertEqual(
            result["shipping_cost"],
            Decimal("50000"),
        )
        self.assertTrue(result["packaging_is_free"])
        self.assertEqual(
            result["packaging_cost"],
            Decimal("0"),
        )

    def test_incomplete_dimensions_are_rejected(self):
        variant = self.create_product_variant(
            weight=1000,
        )

        # شبیه‌سازی داده ناقص در حافظه، بدون نقض constraint دیتابیس
        variant.shipping_length_cm = Decimal("20")
        variant.shipping_width_cm = Decimal("30")
        variant.shipping_height_cm = None

        with self.assertRaises(ShippingCalculationError):
            self.calculate(
                self.method,
                self.city,
                variant,
            )

    def test_missing_shipping_weight_is_rejected(self):
        variant = self.create_product_variant(
            weight=0,
        )

        with self.assertRaises(ShippingCalculationError):
            self.calculate(
                self.method,
                self.city,
                variant,
            )

    def test_snapshot_contains_city_and_rate_information(self):
        result = self.calculate(
            self.method,
            self.city,
            self.variant,
        )

        snapshot = result["snapshot"]

        self.assertEqual(snapshot["city_id"], self.city.id)
        self.assertEqual(snapshot["city_code"], self.city.code)
        self.assertEqual(snapshot["city_name"], self.city.name)
        self.assertEqual(
            snapshot["county_name"],
            self.city.county_name,
        )
        self.assertEqual(
            snapshot["district_name"],
            self.city.district_name,
        )
        self.assertEqual(snapshot["rate_id"], self.rate.id)


class ShippingMethodsAPITests(
    ShippingTestDataMixin,
    APITestCase,
):
    def setUp(self):
        self.city = get_test_tehran_city()

        self.method = self.create_shipping_method()

        self.rate = self.create_shipping_rate(
            self.method,
            cost=50000,
        )

        self.url = reverse("shipping-methods")

    def get_methods(self, **params):
        defaults = {
            "province": self.city.province.slug,
            "city_code": self.city.code,
        }
        defaults.update(params)

        return self.client.get(self.url, defaults)

    def test_city_code_is_required(self):
        response = self.client.get(
            self.url,
            {"province": "tehran"},
        )

        self.assertEqual(response.status_code, 400)

    def test_province_is_required(self):
        response = self.client.get(
            self.url,
            {"city_code": self.city.code},
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_city_code_is_rejected(self):
        response = self.get_methods(
            city_code="INVALID-CITY",
        )

        self.assertEqual(response.status_code, 400)

    def test_city_from_another_province_is_rejected(self):
        response = self.get_methods(
            province="alborz",
        )

        self.assertEqual(response.status_code, 400)

    def test_province_rate_is_returned_when_city_rate_is_missing(self):
        response = self.get_methods()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["slug"],
            self.method.slug,
        )
        self.assertEqual(
            response.data[0]["cost"],
            50000,
        )

    def test_city_rate_is_returned_instead_of_province_rate(self):
        self.create_shipping_rate(
            self.method,
            city=self.city,
            cost=20000,
        )

        response = self.get_methods()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["cost"],
            20000,
        )

    def test_inactive_city_rate_blocks_province_fallback(self):
        self.create_shipping_rate(
            self.method,
            city=self.city,
            cost=20000,
            is_active=False,
        )

        response = self.get_methods()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_inactive_province_rate_is_not_returned(self):
        self.rate.is_active = False
        self.rate.save(update_fields=["is_active"])

        response = self.get_methods()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_method_restricted_to_another_city_is_not_returned(self):
        other_city = City.objects.create(
            province=self.city.province,
            code="TSTTEH003",
            name="شهر دیگر",
            county_name="تهران",
            district_name="مرکزی",
            is_active=True,
        )

        self.method.restricted_city = other_city
        self.method.restricted_province = "tehran"
        self.method.save()

        response = self.get_methods()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_method_restricted_to_selected_city_is_returned(self):
        self.method.restricted_city = self.city
        self.method.restricted_province = "tehran"
        self.method.save()

        response = self.get_methods()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(
            response.data[0]["slug"],
            self.method.slug,
        )

    def test_method_restricted_to_another_province_is_not_returned(self):
        self.method.restricted_province = "alborz"
        self.method.save()

        response = self.get_methods()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])

    def test_inactive_method_is_not_returned(self):
        self.method.is_active = False
        self.method.save(update_fields=["is_active"])

        response = self.get_methods()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])



class ShippingSeedCommandTests(APITestCase):
    def setUp(self):
        self.province = Province.objects.create(
            slug="hamedan",
            name="همدان",
            source_code="TEST-HAM",
            is_active=True,
        )
        self.hamadan_city = City.objects.create(
            province=self.province,
            code="TSTHAM001",
            name="همدان",
            county_name="همدان",
            district_name="مرکزی",
            is_active=True,
        )
        self.other_city = City.objects.create(
            province=self.province,
            code="TSTHAM002",
            name="ملایر",
            county_name="ملایر",
            district_name="مرکزی",
            is_active=True,
        )
        self.url = reverse("shipping-methods")

    def test_seed_command_restricts_motorcycle_to_hamadan_city(self):
        ShippingMethod.objects.create(
            name="پیک قدیمی",
            slug="motorcycle",
            restricted_province="hamedan",
            restricted_city=self.other_city,
        )

        call_command("seed_shipping")

        motorcycle = ShippingMethod.objects.get(slug="motorcycle")
        self.assertEqual(motorcycle.restricted_city_id, self.hamadan_city.pk)
        self.assertEqual(motorcycle.restricted_province, "hamedan")

        hamadan_response = self.client.get(
            self.url,
            {"province": "hamedan", "city_code": self.hamadan_city.code},
        )
        other_city_response = self.client.get(
            self.url,
            {"province": "hamedan", "city_code": self.other_city.code},
        )

        self.assertEqual(hamadan_response.status_code, 200)
        self.assertIn(
            "motorcycle",
            [item["slug"] for item in hamadan_response.data],
        )
        self.assertEqual(other_city_response.status_code, 200)
        self.assertNotIn(
            "motorcycle",
            [item["slug"] for item in other_city_response.data],
        )

    def test_seed_command_fails_when_hamadan_city_is_missing(self):
        self.hamadan_city.delete()

        with self.assertRaises(CommandError):
            call_command("seed_shipping")
