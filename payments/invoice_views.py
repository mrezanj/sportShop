from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from .models import Invoice


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def invoice_detail(request, order_number):
    invoice = (
        Invoice.objects.select_related("order", "payment")
        .filter(order__order_number=order_number, order__user=request.user)
        .first()
    )
    if invoice is None:
        # Do not reveal whether another customer's invoice exists.
        return Response({"detail": "فاکتور یافت نشد."}, status=404)

    return Response({
        "invoice_number": invoice.invoice_number,
        "issued_at": invoice.issued_at,
        "snapshot": invoice.snapshot,
    })
