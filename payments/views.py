from django.shortcuts import get_object_or_404, render, redirect
from django.conf import settings
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from orders.models import Order
from .models import Payment
from .gateways import get_gateway


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def initiate_payment(request):
    order_number = request.data.get('order_number')
    if not order_number:
        return Response(
            {'error': 'شماره سفارش الزامی است.'}, status=400
        )

    try:
        order = Order.objects.get(
            order_number=order_number, user=request.user
        )
    except Order.DoesNotExist:
        return Response({'error': 'سفارش یافت نشد.'}, status=404)

    if order.status == 'paid':
        return Response(
            {'error': 'این سفارش قبلاً پرداخت شده است.'}, status=400
        )
    if order.status == 'cancelled':
        return Response(
            {'error': 'این سفارش لغو شده است.'}, status=400
        )

    payment = order.payments.filter(
        status='pending'
    ).order_by('-created_at').first()
    if not payment:
        payment = Payment.objects.create(
            order=order,
            gateway=getattr(settings, 'ACTIVE_PAYMENT_GATEWAY', 'mock'),
            amount=order.total_amount,
            status='pending',
        )

    gateway = get_gateway()
    result = gateway.request(payment)

    if not result.success:
        payment.status = 'failed'
        payment.gateway_response = result.raw_response
        payment.save()
        return Response(
            {'error': result.message or 'خطا در شروع پرداخت.'}, status=500
        )

    payment.authority = result.authority or ''
    payment.gateway_response = result.raw_response
    payment.save()

    return Response(
        {
            'success': True,
            'payment_id': payment.id,
            'redirect_url': result.redirect_url,
        }
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def verify_payment(request):
    order_number = request.data.get('order_number')
    status = request.data.get('status', '')
    authority = request.data.get('authority', '')

    if not order_number:
        return Response(
            {'error': 'شماره سفارش الزامی است.'}, status=400
        )

    try:
        order = Order.objects.get(
            order_number=order_number, user=request.user
        )
    except Order.DoesNotExist:
        return Response({'error': 'سفارش یافت نشد.'}, status=404)

    if order.status == 'paid':
        return Response({'success': True, 'already_paid': True})

    payment = order.payments.filter(
        status='pending'
    ).order_by('-created_at').first()
    if not payment:
        return Response(
            {'error': 'پرداخت در انتظار یافت نشد.'}, status=400
        )

    gateway = get_gateway()
    result = gateway.verify(
        payment, params={'status': status, 'authority': authority}
    )

    if result.success:
        payment.status = 'success'
        payment.ref_id = result.ref_id or ''
        payment.paid_at = timezone.now()
        payment.gateway_response = result.raw_response
        payment.save()

        order.status = 'paid'
        order.save(update_fields=['status', 'updated_at'])

        return Response(
            {
                'success': True,
                'ref_id': payment.ref_id,
                'order_number': order.order_number,
            }
        )

    payment.status = 'cancelled' if status == 'cancelled' else 'failed'
    payment.gateway_response = result.raw_response
    payment.save()

    return Response(
        {
            'success': False,
            'message': result.message or 'پرداخت ناموفق بود.',
        }
    )


def mock_payment_page(request, payment_id):
    """Mock bank page. Acts as the payment gateway UI."""
    payment = get_object_or_404(Payment, id=payment_id)
    order = payment.order

    if payment.status != 'pending':
        return render(
            request,
            'payments/mock_already_processed.html',
            {'payment': payment, 'order': order},
        )

    if request.method == 'POST':
        status = request.POST.get('status', 'cancelled')
        frontend_url = settings.FRONTEND_URL
        return redirect(
            f'{frontend_url}/checkout/callback'
            f'?order={order.order_number}'
            f'&status={status}'
            f'&authority={payment.authority}'
        )

    return render(
        request,
        'payments/mock_payment.html',
        {'payment': payment, 'order': order},
    )