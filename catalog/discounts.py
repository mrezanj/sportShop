from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from rest_framework.exceptions import ValidationError

from .models import DiscountCampaign, DiscountRedemption


ZERO = Decimal("0")
ONE = Decimal("1")


def _rounded(value):
    return value.quantize(ONE, rounding=ROUND_HALF_UP)


def _eligible_lines(campaign, lines):
    if campaign.scope == "cart":
        return list(lines)
    result = []
    for line in lines:
        product = line["variant"].product
        if campaign.scope == "product" and product.pk == campaign.product_id:
            result.append(line)
        elif campaign.scope == "category" and product.category_id == campaign.category_id:
            result.append(line)
        elif campaign.scope == "brand" and product.brand_id == campaign.brand_id:
            result.append(line)
    return result


def _allocate_cart_discount(amount, eligible_lines):
    remaining_total = sum((line["remaining"] for line in eligible_lines), ZERO)
    if amount <= ZERO or remaining_total <= ZERO:
        return {}
    allocations = {}
    fractions = []
    allocated = ZERO
    for line in eligible_lines:
        exact = amount * line["remaining"] / remaining_total
        floor_value = exact.quantize(ONE, rounding=ROUND_FLOOR)
        floor_value = min(floor_value, line["remaining"])
        allocations[line["variant"].pk] = floor_value
        allocated += floor_value
        fractions.append((exact - floor_value, line["variant"].pk))
    remainder = int(amount - allocated)
    for _, variant_id in sorted(fractions, key=lambda item: (-item[0], item[1])):
        if remainder <= 0:
            break
        line = next(item for item in eligible_lines if item["variant"].pk == variant_id)
        if allocations[variant_id] < line["remaining"]:
            allocations[variant_id] += ONE
            remainder -= 1
    if remainder:
        raise ValidationError({"discount_code": "تقسیم مبلغ تخفیف ممکن نیست؛ با پشتیبانی تماس بگیرید."})
    return allocations


def calculate_discounts(*, user, variants, quantities, discount_code="", now=None, lock=False):
    """
    Calculate deterministic discount allocations using current database state.
    Product/category/brand fixed discounts are per unit; cart fixed discounts
    apply once to the eligible cart subtotal. All values are integer Toman.
    """
    now = now or timezone.now()
    code = (discount_code or "").strip().upper()
    variants_by_id = {variant.pk: variant for variant in variants}
    lines = []
    for variant_id, quantity in sorted(quantities.items()):
        variant = variants_by_id[variant_id]
        gross = variant.price * quantity
        lines.append({
            "variant": variant,
            "quantity": quantity,
            "gross": gross,
            "discount": ZERO,
            "remaining": gross,
        })
    gross_subtotal = sum((line["gross"] for line in lines), ZERO)

    if not lines:
        return {
            "subtotal": ZERO, "discount_amount": ZERO,
            "discounted_subtotal": ZERO, "lines": [],
            "discounts": [], "_campaigns": [],
        }

    queryset = DiscountCampaign.objects.filter(
        is_active=True,
        starts_at__lte=now,
        ends_at__gt=now,
    ).filter(Q(code__isnull=True) | Q(code=""))
    if code:
        queryset = DiscountCampaign.objects.filter(
            Q(is_active=True),
            Q(starts_at__lte=now),
            Q(ends_at__gt=now),
            Q(code__isnull=True) | Q(code="") | Q(code=code),
        )
    queryset = queryset.order_by("-priority", "id")
    if lock:
        queryset = queryset.select_for_update()

    campaigns = list(queryset)
    if code and not any(campaign.code == code for campaign in campaigns):
        raise ValidationError({"discount_code": "کد تخفیف معتبر یا فعال نیست."})

    first_purchase = None
    applied = []
    applied_campaigns = []
    applied_ids = set()

    for campaign in campaigns:
        if campaign.code and campaign.code != code:
            continue
        if campaign.max_uses is not None and campaign.usage_count >= campaign.max_uses:
            if campaign.code == code:
                raise ValidationError({"discount_code": "ظرفیت استفاده از این کد تکمیل شده است."})
            continue
        if campaign.per_user_limit is not None:
            used_by_user = DiscountRedemption.objects.filter(
                campaign=campaign,
                user=user,
                status__in=["reserved", "consumed"],
            ).count()
            if used_by_user >= campaign.per_user_limit:
                if campaign.code == code:
                    raise ValidationError({"discount_code": "سقف استفاده شما از این کد تکمیل شده است."})
                continue
        if campaign.first_purchase_only:
            if first_purchase is None:
                from orders.models import Order
                first_purchase = not Order.objects.filter(user=user).filter(
                    Q(status="paid") | Q(payments__status="success")
                ).exists()
            if not first_purchase:
                if campaign.code == code:
                    raise ValidationError({"discount_code": "این کد فقط برای اولین خرید قابل استفاده است."})
                continue
        if gross_subtotal < campaign.minimum_order_amount:
            if campaign.code == code:
                raise ValidationError({"discount_code": "حداقل مبلغ سبد برای این کد تخفیف رعایت نشده است."})
            continue
        if applied and (
            not campaign.is_stackable
            or any(not item["is_stackable"] for item in applied)
        ):
            if campaign.code == code:
                raise ValidationError({"discount_code": "این کد با تخفیف‌های اولویت‌دار سبد قابل ترکیب نیست."})
            continue

        eligible = _eligible_lines(campaign, lines)
        eligible = [line for line in eligible if line["remaining"] > ZERO]
        if campaign.code == code and not eligible:
            raise ValidationError({"discount_code": "این کد برای محصولات موجود در سبد خرید قابل استفاده نیست."})
        eligible_subtotal = sum((line["remaining"] for line in eligible), ZERO)
        if eligible_subtotal <= ZERO:
            continue

        if campaign.scope == "cart":
            if campaign.discount_type == "percent":
                amount = _rounded(eligible_subtotal * campaign.value / Decimal("100"))
            else:
                amount = min(campaign.value, eligible_subtotal)
            if campaign.maximum_discount_amount is not None:
                amount = min(amount, campaign.maximum_discount_amount)
            amount = min(amount, eligible_subtotal)
            allocations = _allocate_cart_discount(amount, eligible)
        else:
            allocations = {}
            remaining_cap = campaign.maximum_discount_amount
            for line in eligible:
                if campaign.discount_type == "percent":
                    line_amount = _rounded(
                        line["remaining"] * campaign.value / Decimal("100")
                    )
                else:
                    line_amount = campaign.value * line["quantity"]
                if remaining_cap is not None:
                    line_amount = min(line_amount, remaining_cap)
                    remaining_cap -= line_amount
                line_amount = min(line_amount, line["remaining"])
                if line_amount > ZERO:
                    allocations[line["variant"].pk] = line_amount
            amount = sum(allocations.values(), ZERO)

        if amount <= ZERO:
            if campaign.code == code:
                raise ValidationError({"discount_code": "مبلغ تخفیف این کد برای سبد فعلی قابل اعمال نیست."})
            continue
        for line in lines:
            allocated = allocations.get(line["variant"].pk, ZERO)
            if allocated:
                line["discount"] += allocated
                line["remaining"] -= allocated

        applied.append({
            "campaign_id": campaign.pk,
            "name": campaign.name,
            "code": campaign.code or "",
            "scope": campaign.scope,
            "discount_type": campaign.discount_type,
            "value": str(campaign.value),
            "priority": campaign.priority,
            "discount_amount": int(amount),
            "is_stackable": campaign.is_stackable,
        })
        applied_ids.add(campaign.pk)
        applied_campaigns.append(campaign)

    discount_total = sum((line["discount"] for line in lines), ZERO)
    result_lines = [
        {
            "variant_id": line["variant"].pk,
            "quantity": line["quantity"],
            "unit_price": int(line["variant"].price),
            "gross_subtotal": int(line["gross"]),
            "discount_amount": int(line["discount"]),
            "line_subtotal": int(line["remaining"]),
        }
        for line in lines
    ]
    return {
        "subtotal": int(gross_subtotal),
        "discount_amount": int(discount_total),
        "discounted_subtotal": int(gross_subtotal - discount_total),
        "lines": result_lines,
        "discounts": [
            {key: value for key, value in item.items() if key != "is_stackable"}
            for item in applied
        ],
        "campaign_ids": sorted(applied_ids),
        "_campaigns": applied_campaigns,
        "_applied": applied,
    }


@transaction.atomic
def record_discount_redemptions(*, result, order, user, discount_code=""):
    for campaign in result.get("_campaigns", []):
        locked = DiscountCampaign.objects.select_for_update().get(pk=campaign.pk)
        if locked.max_uses is not None and locked.usage_count >= locked.max_uses:
            raise ValidationError({"discount_code": "ظرفیت استفاده از تخفیف هم‌زمان تکمیل شده است؛ دوباره قیمت را بررسی کنید."})
        if locked.per_user_limit is not None:
            used = DiscountRedemption.objects.filter(
                campaign=locked,
                user=user,
                status__in=["reserved", "consumed"],
            ).count()
            if used >= locked.per_user_limit:
                raise ValidationError({"discount_code": "سقف استفاده شما از تخفیف تکمیل شده است."})
        locked.usage_count += 1
        locked.save(update_fields=["usage_count", "updated_at"])
        amount = next(
            Decimal(item["discount_amount"])
            for item in result["_applied"]
            if item["campaign_id"] == locked.pk
        )
        DiscountRedemption.objects.create(
            campaign=locked,
            order=order,
            user=user,
            discount_amount=amount,
            code_used=locked.code or "",
        )
