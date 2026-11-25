from django.conf import settings
from django.db import transaction

from .models import Invoice


def _invoice_number(order):
    created = order.created_at
    return f"INV-{created:%y%m%d}-{order.pk:08d}"


@transaction.atomic
def issue_invoice(order, payment):
    """
    Create the customer's immutable internal sales invoice once payment and
    order completion have been confirmed. The caller must invoke this inside
    the payment-completion transaction.
    """
    existing = Invoice.objects.select_for_update().filter(order=order).first()
    if existing:
        return existing

    if order.status != "paid" or payment.status != "success":
        raise ValueError("An invoice can only be issued for a paid order.")

    pricing = order.pricing_snapshot or {}
    sku_by_variant = {
        str(item.get("variant_id")): item.get("sku", "")
        for item in pricing.get("items", [])
    }

    items = []
    for item in order.items.all().order_by("id"):
        sku = sku_by_variant.get(str(item.variant_id), "") if item.variant_id else ""
        items.append({
            "order_item_id": item.pk,
            "sku": sku,
            "product_name": item.product_name,
            "product_slug": item.product_slug,
            "brand_name": item.brand_name,
            "variant_label": item.variant_label,
            "quantity": item.quantity,
            "unit_price": str(item.price),
            "subtotal": str(item.subtotal),
            "discount_amount": str(item.discount_amount),
            "final_subtotal": str(item.subtotal - item.discount_amount),
        })

    seller = {
        "name": getattr(settings, "INVOICE_SELLER_NAME", ""),
        "national_id": getattr(settings, "INVOICE_SELLER_NATIONAL_ID", ""),
        "economic_code": getattr(settings, "INVOICE_SELLER_ECONOMIC_CODE", ""),
        "registration_number": getattr(settings, "INVOICE_SELLER_REGISTRATION_NUMBER", ""),
        "phone": getattr(settings, "INVOICE_SELLER_PHONE", ""),
        "address": getattr(settings, "INVOICE_SELLER_ADDRESS", ""),
        "postal_code": getattr(settings, "INVOICE_SELLER_POSTAL_CODE", ""),
    }
    buyer = {
        "type": "individual",
        "name": f"{order.first_name} {order.last_name}".strip(),
        "mobile": order.mobile,
        "province": order.get_province_display(),
        "city": order.city,
        "address": order.address,
        "postal_code": order.postal_code,
    }
    snapshot = {
        "document_type": "internal_sales_invoice",
        "official_tax_invoice": False,
        "notice": (
            "این سند فاکتور فروش داخلی است و صورتحساب رسمی ثبت‌شده در "
            "سامانه مؤدیان مالیاتی محسوب نمی‌شود."
        ),
        "currency": "تومان",
        "invoice_number": _invoice_number(order),
        "order_number": order.order_number,
        "issued_at": None,
        "seller": seller,
        "buyer": buyer,
        "items": items,
        "totals": {
            "subtotal": str(order.subtotal),
            "discount_amount": str(order.discount_amount),
            "vat_amount": str(order.vat_amount),
            "shipping_cost": str(order.shipping_cost),
            "packaging_cost": str(order.packaging_cost),
            "total_amount": str(order.total_amount),
        },
        "tax": {
            "rate": pricing.get("vat_rate", ""),
            "amount": str(order.vat_amount),
            "description": "مالیات محاسبه‌شده در زمان ثبت سفارش",
        },
        "payment": {
            "gateway": payment.gateway,
            "reference": payment.ref_id,
            "paid_at": payment.paid_at.isoformat() if payment.paid_at else None,
            "amount": str(payment.amount),
        },
    }

    invoice = Invoice.objects.create(
        order=order,
        payment=payment,
        invoice_number=_invoice_number(order),
        snapshot=snapshot,
    )
    snapshot["issued_at"] = invoice.issued_at.isoformat()
    Invoice.objects.filter(pk=invoice.pk).update(snapshot=snapshot)
    invoice.snapshot = snapshot
    return invoice
