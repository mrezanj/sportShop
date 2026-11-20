from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from .serializers import RequestOTPSerializer, VerifyOTPSerializer


@api_view(['POST'])
@permission_classes([AllowAny])
def request_otp(request):
    serializer = RequestOTPSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = serializer.save()
    return Response({
        'success': True,
        'message': 'کد تایید ارسال شد.',
        **result,
    })


@api_view(['POST'])
@permission_classes([AllowAny])
def verify_otp(request):
    serializer = VerifyOTPSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    token, _ = Token.objects.get_or_create(user=user)
    profile = getattr(user, 'profile', None)
    return Response({
        'success': True,
        'token': token.key,
        'user': {
            'id': user.id,
            'mobile': profile.mobile if profile else None,
        },
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    user = request.user
    profile = getattr(user, 'profile', None)
    return Response({
        'id': user.id,
        'mobile': profile.mobile if profile else None,
        'is_staff': user.is_staff,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout(request):
    if hasattr(request.user, 'auth_token'):
        request.user.auth_token.delete()
    return Response({'success': True})