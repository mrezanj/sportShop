
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase

from catalog.models import Brand, Category, Product, ProductVariant
from orders.models import (
    Order,
    OrderItem,
    ShippingMethod,
    ShippingRate,
    StockReservation,
)
from cart.models import Cart, CartItem


class CartAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="cart-user",
            password="test-password",
        )

        self.other_user = User.objects.create_user(
            username="other-cart-user",
            password="test-password",
        )

        self.brand = Brand.objects.create(
            name="Cart Brand",
            slug="cart-brand",
        )

        self.category = Category.objects.create(
            name="Cart Category",
            slug="cart-category",
        )

        self.product = Product.objects.create(
            name_fa="محصول سبد خرید",
            slug="cart-product",
            brand=self.brand,
            category=self.category,
            description="توضیحات محصول آزمایشی",
        )

        self.variant = ProductVariant.objects.create(
            product=self.product,
            price=Decimal("100000"),
            stock=5,
        )

        self.shipping_method = ShippingMethod.objects.create(
            name="ارسال آزمایشی",
            slug="test-shipping",
        )

        ShippingRate.objects.create(
            method=self.shipping_method,
            province="tehran",
            cost=Decimal("50000"),
        )

        self.client.force_authenticate(user=self.user)

        self.cart_url = reverse("cart-detail")
        self.add_url = reverse("cart-add-item")
        self.checkout_url = reverse("cart-checkout")

    def add_item(self, quantity=1):
        return self.client.post(
            self.add_url,
            {
                "variant_id": self.variant.id,
                "quantity": quantity,
            },
            format="json",
        )

    def create_reservation(self, quantity):
        expires_at = timezone.now() + timedelta(minutes=30)

        order = Order.objects.create(
            user=self.other_user,
            first_name="Test",
            last_name="User",
            mobile="09123456789",
            province="tehran",
            city="تهران",
            address="آدرس آزمایشی معتبر",
            subtotal=Decimal(quantity * 100000),
            vat_amount=Decimal(quantity * 10000),
            total_amount=Decimal(quantity * 110000 + 50000),
            status="pending",
            reservation_expires_at=expires_at,
        )

        return StockReservation.objects.create(
            order=order,
            variant=self.variant,
            quantity=quantity,
            status="active",
            expires_at=expires_at,
        )

    def checkout_payload(self):
        return {
            "shipping_method_slug": "test-shipping",
            "province": "tehran",
            "city": "تهران",
            "address": "آدرس آزمایشی معتبر برای ثبت سفارش",
            "postal_code": "1234567890",
            "first_name": "Test",
            "last_name": "User",
            "mobile": "09123456789",
            "notes": "",
        }

    def test_authenticated_user_can_view_empty_cart(self):
        response = self.client.get(self.cart_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["total_quantity"], 0)
        self.assertEqual(Decimal(response.data["subtotal"]), Decimal("0"))

        self.assertTrue(
            Cart.objects.filter(user=self.user).exists()
        )

    def test_user_can_add_item_to_cart(self):
        response = self.add_item(quantity=2)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["quantity"], 2)

        item = CartItem.objects.get(
            cart__user=self.user,
            variant=self.variant,
        )

        self.assertEqual(item.quantity, 2)

    def test_adding_existing_variant_increases_quantity(self):
        first_response = self.add_item(quantity=1)
        second_response = self.add_item(quantity=2)

        self.assertEqual(first_response.status_code, 201)
        self.assertEqual(second_response.status_code, 201)

        item = CartItem.objects.get(
            cart__user=self.user,
            variant=self.variant,
        )

        self.assertEqual(item.quantity, 3)
        self.assertEqual(CartItem.objects.filter(cart=item.cart).count(), 1)

    def test_user_cannot_add_more_than_available_stock(self):
        response = self.add_item(quantity=6)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            CartItem.objects.filter(cart__user=self.user).exists()
        )

    def test_active_reservations_reduce_available_cart_stock(self):
        self.create_reservation(quantity=3)

        response = self.add_item(quantity=3)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            CartItem.objects.filter(cart__user=self.user).exists()
        )

    def test_expired_reservations_do_not_reduce_available_cart_stock(self):
        reservation = self.create_reservation(quantity=3)

        StockReservation.objects.filter(pk=reservation.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1)
        )

        response = self.add_item(quantity=5)

        self.assertEqual(response.status_code, 201)

        item = CartItem.objects.get(cart__user=self.user)
        self.assertEqual(item.quantity, 5)

    def test_user_cannot_add_inactive_variant(self):
        self.variant.is_active = False
        self.variant.save(update_fields=["is_active"])

        response = self.add_item(quantity=1)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            CartItem.objects.filter(cart__user=self.user).exists()
        )

    def test_user_can_update_cart_item_quantity(self):
        self.add_item(quantity=2)

        item = CartItem.objects.get(cart__user=self.user)

        response = self.client.patch(
            reverse("cart-update-item", args=[item.id]),
            {"quantity": 4},
            format="json",
        )

        self.assertEqual(response.status_code, 200)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 4)

    def test_user_cannot_update_quantity_above_available_stock(self):
        self.add_item(quantity=2)

        item = CartItem.objects.get(cart__user=self.user)

        response = self.client.patch(
            reverse("cart-update-item", args=[item.id]),
            {"quantity": 6},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

        item.refresh_from_db()
        self.assertEqual(item.quantity, 2)

    def test_user_cannot_update_another_users_cart_item(self):
        other_cart = Cart.objects.create(user=self.other_user)

        other_item = CartItem.objects.create(
            cart=other_cart,
            variant=self.variant,
            quantity=1,
        )

        response = self.client.patch(
            reverse("cart-update-item", args=[other_item.id]),
            {"quantity": 2},
            format="json",
        )

        self.assertEqual(response.status_code, 404)

        other_item.refresh_from_db()
        self.assertEqual(other_item.quantity, 1)

    def test_user_can_remove_cart_item(self):
        self.add_item(quantity=2)

        item = CartItem.objects.get(cart__user=self.user)

        response = self.client.delete(
            reverse("cart-remove-item", args=[item.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            CartItem.objects.filter(pk=item.id).exists()
        )

    def test_user_cannot_remove_another_users_cart_item(self):
        other_cart = Cart.objects.create(user=self.other_user)

        other_item = CartItem.objects.create(
            cart=other_cart,
            variant=self.variant,
            quantity=1,
        )

        response = self.client.delete(
            reverse("cart-remove-item", args=[other_item.id])
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(
            CartItem.objects.filter(pk=other_item.id).exists()
        )

    def test_user_can_clear_cart(self):
        self.add_item(quantity=1)

        response = self.client.delete(
            reverse("cart-clear")
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            CartItem.objects.filter(cart__user=self.user).exists()
        )

    def test_cart_is_isolated_between_users(self):
        self.add_item(quantity=2)

        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(self.cart_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["items"], [])
        self.assertEqual(response.data["total_quantity"], 0)

        self.assertEqual(
            CartItem.objects.filter(cart__user=self.user).count(),
            1,
        )

    def test_cart_uses_current_variant_price(self):
        self.add_item(quantity=2)

        self.variant.price = Decimal("150000")
        self.variant.save(update_fields=["price"])

        response = self.client.get(self.cart_url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Decimal(response.data["items"][0]["price"]),
            Decimal("150000"),
        )
        self.assertEqual(
            Decimal(response.data["items"][0]["subtotal"]),
            Decimal("300000"),
        )
        self.assertEqual(
            Decimal(response.data["subtotal"]),
            Decimal("300000"),
        )

    def test_checkout_creates_order_and_clears_cart(self):
        self.add_item(quantity=2)

        response = self.client.post(
            self.checkout_url,
            self.checkout_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        order = Order.objects.get(order_number=response.data["order_number"])

        self.assertEqual(order.user, self.user)
        self.assertEqual(order.status, "pending")

        order_item = OrderItem.objects.get(order=order)

        self.assertEqual(order_item.variant, self.variant)
        self.assertEqual(order_item.quantity, 2)
        self.assertEqual(order_item.price, Decimal("100000"))

        reservation = StockReservation.objects.get(order=order)

        self.assertEqual(reservation.quantity, 2)
        self.assertEqual(reservation.status, "active")

        self.assertFalse(
            CartItem.objects.filter(cart__user=self.user).exists()
        )

    def test_checkout_ignores_client_supplied_items(self):
        self.add_item(quantity=1)

        payload = self.checkout_payload()
        payload["items"] = [
            {
                "variant_id": self.variant.id,
                "quantity": 5,
            }
        ]

        response = self.client.post(
            self.checkout_url,
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 201)

        order = Order.objects.get(order_number=response.data["order_number"])
        order_item = OrderItem.objects.get(order=order)

        self.assertEqual(order_item.quantity, 1)

    def test_failed_checkout_keeps_cart_items(self):
        self.add_item(quantity=2)

        payload = self.checkout_payload()
        payload["shipping_method_slug"] = "invalid-shipping"

        response = self.client.post(
            self.checkout_url,
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, 400)

        item = CartItem.objects.get(cart__user=self.user)
        self.assertEqual(item.quantity, 2)

        self.assertEqual(Order.objects.filter(user=self.user).count(), 0)

    def test_checkout_with_insufficient_stock_keeps_cart_items(self):
        self.add_item(quantity=2)

        self.create_reservation(quantity=4)

        response = self.client.post(
            self.checkout_url,
            self.checkout_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 400)

        item = CartItem.objects.get(cart__user=self.user)
        self.assertEqual(item.quantity, 2)

        self.assertEqual(Order.objects.filter(user=self.user).count(), 0)

    def test_checkout_rejects_empty_cart(self):
        response = self.client.post(
            self.checkout_url,
            self.checkout_payload(),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.filter(user=self.user).count(), 0)

    def test_unauthenticated_user_cannot_access_cart(self):
        self.client.force_authenticate(user=None)

        get_response = self.client.get(self.cart_url)
        post_response = self.add_item(quantity=1)

        self.assertEqual(get_response.status_code, 401)
        self.assertEqual(post_response.status_code, 401)
