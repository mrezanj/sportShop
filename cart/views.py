
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from catalog.models import ProductVariant
from orders.serializers import CreateOrderSerializer
from .models import Cart, CartItem
from .serializers import (
    CartSerializer,
    AddCartItemSerializer,
    UpdateCartItemSerializer,
)
from inventory.services import get_variant_inventory


def get_user_cart(user):
    cart, _ = Cart.objects.get_or_create(user=user)
    return cart


def get_available_stock(variant):
    inventory = get_variant_inventory(variant)
    return inventory["available"]


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def cart_detail(request):
    cart = get_user_cart(request.user)

    cart = (
        Cart.objects.filter(pk=cart.pk)
        .prefetch_related(
            "items__variant__product__brand",
            "items__variant__product__images",
        )
        .get()
    )

    serializer = CartSerializer(
        cart,
        context={"request": request},
    )
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def add_cart_item(request):
    serializer = AddCartItemSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    variant_id = serializer.validated_data["variant"].pk
    quantity = serializer.validated_data["quantity"]

    with transaction.atomic():
        cart = get_user_cart(request.user)
        cart = Cart.objects.select_for_update().get(pk=cart.pk)

        variant = get_object_or_404(
            ProductVariant.objects.select_for_update().select_related("product"),
            pk=variant_id,
            is_active=True,
            product__is_active=True,
        )

        available_stock = get_available_stock(variant)

        item = (
            CartItem.objects.select_for_update()
            .filter(
                cart=cart,
                variant=variant,
            )
            .first()
        )

        current_quantity = item.quantity if item else 0
        new_quantity = current_quantity + quantity

        if new_quantity > available_stock:
            raise ValidationError(
                {
                    "quantity": (
                        f"موجودی قابل خرید: "
                        f"{max(available_stock - current_quantity, 0)}"
                    )
                }
            )

        if item:
            item.quantity = new_quantity
            item.save(update_fields=["quantity", "updated_at"])
        else:
            item = CartItem.objects.create(
                cart=cart,
                variant=variant,
                quantity=quantity,
            )

    return Response(
        {
            "success": True,
            "message": "محصول به سبد خرید اضافه شد.",
            "item_id": item.id,
            "quantity": item.quantity,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def update_cart_item(request, item_id):
    serializer = UpdateCartItemSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    quantity = serializer.validated_data["quantity"]

    with transaction.atomic():
        cart = Cart.objects.filter(user=request.user).first()

        if cart is None:
            return Response(
                {"detail": "قلم موردنظر در سبد خرید یافت نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        cart = Cart.objects.select_for_update().get(pk=cart.pk)

        variant_id = (
            CartItem.objects.filter(cart=cart, pk=item_id)
            .values_list("variant_id", flat=True)
            .first()
        )

        if variant_id is None:
            return Response(
                {"detail": "قلم موردنظر در سبد خرید یافت نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        variant = get_object_or_404(
            ProductVariant.objects.select_for_update().select_related("product"),
            pk=variant_id,
            is_active=True,
            product__is_active=True,
        )

        item = get_object_or_404(
            CartItem.objects.select_for_update(),
            pk=item_id,
            cart=cart,
        )

        available_stock = get_available_stock(variant)

        if quantity > available_stock:
            raise ValidationError({"quantity": f"موجودی قابل خرید: {available_stock}"})

        item.quantity = quantity
        item.save(update_fields=["quantity", "updated_at"])

    return Response(
        {
            "success": True,
            "message": "تعداد محصول به‌روزرسانی شد.",
            "item_id": item.id,
            "quantity": item.quantity,
        }
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def remove_cart_item(request, item_id):
    with transaction.atomic():
        cart = Cart.objects.filter(user=request.user).first()

        if cart is None:
            return Response(
                {"detail": "قلم موردنظر در سبد خرید یافت نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        cart = Cart.objects.select_for_update().get(pk=cart.pk)

        item = (
            CartItem.objects.select_for_update()
            .filter(
                cart=cart,
                pk=item_id,
            )
            .first()
        )

        if item is None:
            return Response(
                {"detail": "قلم موردنظر در سبد خرید یافت نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        item.delete()

    return Response(
        {
            "success": True,
            "message": "محصول از سبد خرید حذف شد.",
        }
    )


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def clear_cart(request):
    with transaction.atomic():
        cart = get_user_cart(request.user)
        cart = Cart.objects.select_for_update().get(pk=cart.pk)

        items = CartItem.objects.select_for_update().filter(cart=cart)
        items.delete()

    return Response(
        {
            "success": True,
            "message": "سبد خرید خالی شد.",
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def checkout(request):
    with transaction.atomic():
        cart = get_user_cart(request.user)
        cart = Cart.objects.select_for_update().get(pk=cart.pk)

        cart_items = list(
            CartItem.objects.select_for_update()
            .filter(cart=cart)
            .order_by("variant_id")
        )

        if not cart_items:
            raise ValidationError({"cart": "سبد خرید شما خالی است."})

        items = [
            {
                "variant_id": item.variant_id,
                "quantity": item.quantity,
            }
            for item in cart_items
        ]

        payload = {
            "items": items,
            "shipping_method_slug": request.data.get("shipping_method_slug"),
            "province": request.data.get("province"),
            "city_code": request.data.get("city_code"),
            "address": request.data.get("address"),
            "postal_code": request.data.get("postal_code", ""),
            "first_name": request.data.get("first_name"),
            "last_name": request.data.get("last_name"),
            "mobile": request.data.get("mobile"),
            "notes": request.data.get("notes", ""),
        }

        serializer = CreateOrderSerializer(
            data=payload,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)

        order = serializer.save()

        cart.items.all().delete()

    return Response(
        {
            "success": True,
            "message": "سفارش شما با موفقیت ثبت شد.",
            "order_number": order.order_number,
            "total_amount": int(order.total_amount),
            "subtotal": int(order.subtotal),
            "vat_amount": int(order.vat_amount),
            "shipping_cost": int(order.shipping_cost),
        },
        status=status.HTTP_201_CREATED,
    )
