from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Order, OrderDiscrepancy, OrderItem, OrderStatusHistory
from .discrepancy_services import (
    DiscrepancyError,
    open_order_discrepancy,
    resolve_order_discrepancy,
)
from .return_services import (
    ReturnRequestError,
    create_return_request,
    review_return_request,
    mark_return_received,
)


class OrderDiscrepancyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("discrepancy-staff")
        self.order = Order.objects.create(
            user=self.user, first_name="Test", last_name="Customer",
            mobile="09123456789", province="tehran", city="Tehran",
            address="Test address", subtotal=Decimal("100000"),
            vat_amount=Decimal("10000"), total_amount=Decimal("110000"),
            status="delivered",
        )

    def test_open_discrepancy_holds_order_and_records_history(self):
        case = open_order_discrepancy(
            order_id=self.order.pk, reason="مغایرت تعداد", actor=self.user
        )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, "discrepancy")
        self.assertEqual(case.previous_order_status, "delivered")
        self.assertEqual(
            OrderStatusHistory.objects.filter(
                order=self.order, new_status="discrepancy"
            ).count(), 1
        )

    def test_only_one_open_discrepancy_is_allowed(self):
        open_order_discrepancy(
            order_id=self.order.pk, reason="مغایرت اول", actor=self.user
        )
        with self.assertRaises(DiscrepancyError):
            open_order_discrepancy(
                order_id=self.order.pk, reason="مغایرت دوم", actor=self.user
            )

    def test_resolving_discrepancy_restores_previous_order_status(self):
        case = open_order_discrepancy(
            order_id=self.order.pk, reason="مغایرت", actor=self.user
        )
        resolve_order_discrepancy(
            case_id=case.pk, resolution="اصلاح شد", actor=self.user
        )
        self.order.refresh_from_db()
        case.refresh_from_db()
        self.assertEqual(self.order.status, "delivered")
        self.assertEqual(case.status, "resolved")
        self.assertEqual(case.resolution, "اصلاح شد")

    def test_discrepancy_requires_resolution_text(self):
        case = open_order_discrepancy(
            order_id=self.order.pk, reason="مغایرت", actor=self.user
        )
        with self.assertRaises(DiscrepancyError):
            resolve_order_discrepancy(case_id=case.pk, resolution="", actor=self.user)


class ReturnRequestTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("return-customer")
        self.staff = User.objects.create_user("return-staff")
        self.order = Order.objects.create(
            user=self.user, first_name="Test", last_name="Customer",
            mobile="09123456789", province="tehran", city="Tehran",
            address="Test address", subtotal=Decimal("200000"),
            vat_amount=Decimal("20000"), total_amount=Decimal("220000"),
            status="paid",
        )
        self.item = OrderItem.objects.create(
            order=self.order, product_name="Test Product",
            product_slug="test-product", brand_name="Test Brand",
            variant_label="Default", price=Decimal("100000"),
            quantity=2, subtotal=Decimal("200000"),
        )

    def test_customer_can_request_partial_quantity(self):
        request = create_return_request(
            order_number=self.order.order_number, user=self.user,
            reason="کالای اشتباه", items=[
                {"order_item_id": self.item.pk, "quantity": 1}
            ],
        )
        self.assertEqual(request.items.get().quantity, 1)
        self.assertEqual(request.status, "requested")

    def test_customer_cannot_return_more_than_purchased(self):
        with self.assertRaises(ReturnRequestError):
            create_return_request(
                order_number=self.order.order_number, user=self.user,
                reason="مرجوعی", items=[
                    {"order_item_id": self.item.pk, "quantity": 3}
                ],
            )

    def test_customer_cannot_request_return_for_unpaid_order(self):
        self.order.status = "pending"
        self.order.save(update_fields=["status"])
        with self.assertRaises(ReturnRequestError):
            create_return_request(
                order_number=self.order.order_number, user=self.user,
                reason="مرجوعی", items=[
                    {"order_item_id": self.item.pk, "quantity": 1}
                ],
            )

    def test_return_review_and_receipt_lifecycle(self):
        request = create_return_request(
            order_number=self.order.order_number, user=self.user,
            reason="مرجوعی", items=[
                {"order_item_id": self.item.pk, "quantity": 1}
            ],
        )
        review_return_request(
            request_id=request.pk, actor=self.staff,
            decision="approved", note="تأیید شد",
        )
        mark_return_received(
            request_id=request.pk, actor=self.staff, note="کالا دریافت شد",
        )
        request.refresh_from_db()
        self.assertEqual(request.status, "received")
        self.assertEqual(request.reviewed_by, self.staff)
        self.assertEqual(list(request.history.values_list("new_status", flat=True)), ["requested", "approved", "received"])

    def test_return_request_cannot_be_reviewed_twice(self):
        request = create_return_request(
            order_number=self.order.order_number, user=self.user,
            reason="مرجوعی", items=[
                {"order_item_id": self.item.pk, "quantity": 1}
            ],
        )
        review_return_request(
            request_id=request.pk, actor=self.staff, decision="rejected"
        )
        with self.assertRaises(ReturnRequestError):
            review_return_request(
                request_id=request.pk, actor=self.staff, decision="approved"
            )



class ReturnPermissionAPITests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user("return-api-customer")
        self.other = User.objects.create_user("return-api-other")
        self.staff = User.objects.create_user("return-api-staff")
        self.order = Order.objects.create(
            user=self.customer, first_name="Test", last_name="Customer",
            mobile="09123456789", province="tehran", city="Tehran",
            address="Test address", subtotal=Decimal("100000"),
            vat_amount=Decimal("10000"), total_amount=Decimal("110000"),
            status="paid",
        )
        self.client = APIClient()

    def test_customer_cannot_create_return_for_another_users_order(self):
        self.client.force_authenticate(user=self.other)
        response = self.client.post("/api/orders/returns/", {
            "order_number": self.order.order_number,
            "reason": "مرجوعی",
            "items": [{"order_item_id": 999, "quantity": 1}],
        }, format="json")
        self.assertEqual(response.status_code, 404)

    def test_return_review_endpoint_requires_explicit_permission(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post("/api/orders/returns/999/review/", {
            "decision": "approved",
        }, format="json")
        self.assertEqual(response.status_code, 403)

    def test_staff_permission_can_list_all_return_requests(self):
        permission = __import__("django.contrib.auth.models", fromlist=["Permission"]).Permission.objects.get(
            content_type__app_label="orders",
            codename="can_review_return_requests",
        )
        self.staff.user_permissions.add(permission)
        self.client.force_authenticate(user=self.staff)
        response = self.client.get("/api/orders/returns/")
        self.assertEqual(response.status_code, 200)
