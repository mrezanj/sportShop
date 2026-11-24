from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APITestCase

from catalog.discounts import calculate_discounts, record_discount_redemptions
from catalog.models import (
    Brand,
    Category,
    DiscountCampaign,
    Product,
    ProductVariant,
    DiscountRedemption,
)


class DiscountCalculationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="discount-customer",
            password="test-password",
        )
        self.brand = Brand.objects.create(name="Discount Brand", slug="discount-brand")
        self.category = Category.objects.create(
            name="Discount Category",
            slug="discount-category",
        )
        self.product = Product.objects.create(
            name_fa="محصول تخفیف",
            slug="discount-product",
            brand=self.brand,
            category=self.category,
            description="Discount test product",
        )
        self.variant = ProductVariant.objects.create(
            product=self.product,
            sku="DISCOUNT-SKU-1",
            price=Decimal("100000"),
        )
        self.second_product = Product.objects.create(
            name_fa="محصول دوم",
            slug="discount-product-2",
            brand=self.brand,
            category=self.category,
            description="Second discount test product",
        )
        self.second_variant = ProductVariant.objects.create(
            product=self.second_product,
            sku="DISCOUNT-SKU-2",
            price=Decimal("200000"),
        )
        self.now = timezone.now()

    def campaign(self, **overrides):
        values = {
            "name": "Campaign",
            "scope": "product",
            "product": self.product,
            "discount_type": "percent",
            "value": Decimal("10"),
            "starts_at": self.now - timedelta(days=1),
            "ends_at": self.now + timedelta(days=1),
            "is_active": True,
        }
        values.update(overrides)
        return DiscountCampaign.objects.create(**values)

    def calculate(self, quantities=None, code=""):
        quantities = quantities or {self.variant.pk: 1}
        variants = list(
            ProductVariant.objects.select_related("product").filter(
                pk__in=quantities
            )
        )
        return calculate_discounts(
            user=self.user,
            variants=variants,
            quantities=quantities,
            discount_code=code,
            now=self.now,
        )

    def test_product_percentage_discount_applies_to_all_units(self):
        self.campaign(value=Decimal("10"))
        result = self.calculate({self.variant.pk: 2})

        self.assertEqual(result["subtotal"], 200000)
        self.assertEqual(result["discount_amount"], 20000)
        self.assertEqual(result["discounted_subtotal"], 180000)
        self.assertEqual(result["lines"][0]["discount_amount"], 20000)

    def test_product_fixed_discount_is_per_unit_and_cannot_exceed_line_total(self):
        self.campaign(discount_type="fixed", value=Decimal("7000"))
        result = self.calculate({self.variant.pk: 2})

        self.assertEqual(result["discount_amount"], 14000)
        self.assertEqual(result["discounted_subtotal"], 186000)

        DiscountCampaign.objects.all().delete()
        self.campaign(discount_type="fixed", value=Decimal("150000"))
        result = self.calculate({self.variant.pk: 1})
        self.assertEqual(result["discount_amount"], 100000)
        self.assertEqual(result["discounted_subtotal"], 0)

    def test_category_and_brand_campaigns_match_their_products(self):
        self.campaign(
            scope="category",
            product=None,
            category=self.category,
            value=Decimal("5"),
        )
        result = self.calculate({self.second_variant.pk: 1})
        self.assertEqual(result["discount_amount"], 10000)

        DiscountCampaign.objects.all().delete()
        self.campaign(
            scope="brand",
            product=None,
            brand=self.brand,
            value=Decimal("5"),
        )
        result = self.calculate({self.second_variant.pk: 1})
        self.assertEqual(result["discount_amount"], 10000)

    def test_cart_fixed_discount_is_allocated_proportionally(self):
        self.campaign(
            scope="cart",
            product=None,
            discount_type="fixed",
            value=Decimal("30000"),
        )
        result = self.calculate({
            self.variant.pk: 1,
            self.second_variant.pk: 1,
        })
        by_id = {item["variant_id"]: item for item in result["lines"]}

        self.assertEqual(result["discount_amount"], 30000)
        self.assertEqual(by_id[self.variant.pk]["discount_amount"], 10000)
        self.assertEqual(by_id[self.second_variant.pk]["discount_amount"], 20000)

    def test_minimum_order_and_maximum_discount_limits_are_enforced(self):
        self.campaign(
            code="CAPPED",
            value=Decimal("50"),
            maximum_discount_amount=Decimal("5000"),
            minimum_order_amount=Decimal("150000"),
        )
        with self.assertRaises(ValidationError):
            self.calculate(code="CAPPED")

        result = self.calculate({self.variant.pk: 2}, code="CAPPED")
        self.assertEqual(result["discount_amount"], 5000)
        self.assertEqual(result["discounted_subtotal"], 195000)

    def test_stackable_campaigns_apply_in_priority_order(self):
        self.campaign(
            name="Product discount",
            priority=200,
            is_stackable=True,
            value=Decimal("10"),
        )
        self.campaign(
            name="Cart discount",
            scope="cart",
            product=None,
            discount_type="percent",
            value=Decimal("10"),
            priority=100,
            is_stackable=True,
        )
        result = self.calculate()

        self.assertEqual(result["discount_amount"], 19000)
        self.assertEqual(
            [item["name"] for item in result["discounts"]],
            ["Product discount", "Cart discount"],
        )

    def test_non_stackable_campaign_blocks_lower_priority_campaigns(self):
        self.campaign(priority=200, is_stackable=False, value=Decimal("10"))
        self.campaign(
            name="Lower priority",
            scope="cart",
            product=None,
            priority=100,
            is_stackable=True,
            value=Decimal("20"),
        )
        result = self.calculate()

        self.assertEqual(result["discount_amount"], 10000)
        self.assertEqual(len(result["discounts"]), 1)

    def test_coupon_code_is_case_insensitive_and_rejects_invalid_code(self):
        self.campaign(code="SAVE10", value=Decimal("10"))
        result = self.calculate(code="save10")
        self.assertEqual(result["discount_amount"], 10000)

        with self.assertRaises(ValidationError):
            self.calculate(code="UNKNOWN")

    def test_first_purchase_campaign_rejects_customer_with_paid_order(self):
        from orders.models import Order

        self.campaign(
            code="FIRSTBUY",
            first_purchase_only=True,
        )
        result = self.calculate(code="FIRSTBUY")
        self.assertEqual(result["discount_amount"], 10000)

        Order.objects.create(
            user=self.user,
            first_name="Test",
            last_name="Customer",
            mobile="09123456789",
            province="tehran",
            city="Tehran",
            address="Test address long enough",
            subtotal=Decimal("100000"),
            vat_amount=Decimal("10000"),
            total_amount=Decimal("110000"),
            status="paid",
        )
        with self.assertRaises(ValidationError):
            self.calculate(code="FIRSTBUY")

    def test_campaign_window_and_global_usage_limit_are_enforced(self):
        self.campaign(
            code="LIMITED",
            max_uses=1,
            usage_count=1,
        )
        with self.assertRaises(ValidationError):
            self.calculate(code="LIMITED")

        DiscountCampaign.objects.all().delete()
        self.campaign(
            code="FUTURE",
            starts_at=self.now + timedelta(days=1),
            ends_at=self.now + timedelta(days=2),
        )
        with self.assertRaises(ValidationError):
            self.calculate(code="FUTURE")


class DiscountCampaignManagementAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="discount-manager",
            password="test-password",
            is_staff=True,
        )
        self.permission = Permission.objects.get(
            content_type__app_label="catalog",
            codename="can_manage_product_prices",
        )
        self.user.user_permissions.add(self.permission)
        self.client.force_authenticate(self.user)
        self.brand = Brand.objects.create(name="API Discount Brand", slug="api-discount-brand")
        self.category = Category.objects.create(
            name="API Discount Category",
            slug="api-discount-category",
        )
        self.product = Product.objects.create(
            name_fa="محصول API تخفیف",
            slug="api-discount-product",
            brand=self.brand,
            category=self.category,
            description="API discount test product",
        )
        self.url = reverse("discount-list")

    def payload(self):
        now = timezone.now()
        return {
            "name": "API campaign",
            "code": "API10",
            "scope": "product",
            "product": self.product.pk,
            "discount_type": "percent",
            "value": "10",
            "minimum_order_amount": "0",
            "starts_at": (now - timedelta(hours=1)).isoformat(),
            "ends_at": (now + timedelta(days=1)).isoformat(),
            "priority": 100,
            "is_stackable": False,
            "first_purchase_only": False,
            "max_uses": 10,
            "per_user_limit": 1,
            "is_active": True,
        }

    def test_authorized_manager_can_create_and_list_campaigns(self):
        response = self.client.post(self.url, self.payload(), format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["code"], "API10")

        listing = self.client.get(self.url)
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(len(listing.data), 1)

    def test_staff_without_price_permission_cannot_manage_campaigns(self):
        self.user.user_permissions.clear()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_invalid_scope_target_is_rejected(self):
        data = self.payload()
        data["scope"] = "cart"
        response = self.client.post(self.url, data, format="json")
        self.assertEqual(response.status_code, 400)



class DiscountRedemptionLifecycleTests(TestCase):
    def setUp(self):
        DiscountCalculationTests.setUp(self)
        from orders.models import Order

        self.order = Order.objects.create(
            user=self.user,
            first_name="Test",
            last_name="Customer",
            mobile="09123456789",
            province="tehran",
            city="Tehran",
            address="Test address long enough",
            subtotal=Decimal("100000"),
            vat_amount=Decimal("9000"),
            discount_amount=Decimal("10000"),
            total_amount=Decimal("99000"),
            status="pending",
        )

    def create_reserved_redemption(self):
        from orders.services import release_order_discount_redemptions

        campaign = self.campaign(code="LIFECYCLE", max_uses=3, per_user_limit=1)
        result = self.calculate(code="LIFECYCLE")
        record_discount_redemptions(
            result=result,
            order=self.order,
            user=self.user,
        )
        campaign.refresh_from_db()
        redemption = DiscountRedemption.objects.get(
            campaign=campaign,
            order=self.order,
        )
        self.assertEqual(campaign.usage_count, 1)
        self.assertEqual(redemption.status, "reserved")
        return campaign, redemption, release_order_discount_redemptions

    def test_cancelled_order_releases_reserved_redemption_and_capacity(self):
        campaign, redemption, release = self.create_reserved_redemption()

        release(self.order)
        campaign.refresh_from_db()
        redemption.refresh_from_db()

        self.assertEqual(campaign.usage_count, 0)
        self.assertEqual(redemption.status, "released")

    def test_releasing_redemption_is_idempotent(self):
        campaign, redemption, release = self.create_reserved_redemption()

        release(self.order)
        release(self.order)
        campaign.refresh_from_db()
        redemption.refresh_from_db()

        self.assertEqual(campaign.usage_count, 0)
        self.assertEqual(redemption.status, "released")

    def test_reserved_first_purchase_offer_blocks_another_first_purchase_offer(self):
        self.campaign(code="FIRST-RESERVED", first_purchase_only=True)
        result = self.calculate(code="FIRST-RESERVED")
        record_discount_redemptions(
            result=result,
            order=self.order,
            user=self.user,
        )

        self.campaign(
            name="Second first purchase campaign",
            code="FIRST-SECOND",
            first_purchase_only=True,
        )
        with self.assertRaises(ValidationError):
            self.calculate(code="FIRST-SECOND")

    def test_successful_payment_consumes_redemption_without_releasing_capacity(self):
        from orders.services import consume_order_discount_redemptions

        campaign, redemption, _ = self.create_reserved_redemption()
        consume_order_discount_redemptions(self.order)
        campaign.refresh_from_db()
        redemption.refresh_from_db()

        self.assertEqual(campaign.usage_count, 1)
        self.assertEqual(redemption.status, "consumed")

        with self.assertRaises(ValidationError):
            self.calculate(code="LIFECYCLE")
