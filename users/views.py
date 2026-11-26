from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from .serializers import RequestOTPSerializer, VerifyOTPSerializer
from .throttles import OTPRequestThrottle, OTPVerifyThrottle
from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from .serializers import (
    RequestOTPSerializer,
    VerifyOTPSerializer,
    ProfileSerializer,
)


BUSINESS_STAFF_GROUPS = (
    "مدیرعامل",
    "رئیس هیئت‌مدیره",
    "مدیر داخلی",
    "حسابدار",
    "مشاور",
)


def _staff_flags(user):
    is_staff = bool(user.is_staff)
    is_employee = is_staff or user.groups.filter(
        name__in=BUSINESS_STAFF_GROUPS
    ).exists()
    can_manage_staff = bool(
        user.is_superuser
        or user.groups.filter(name__in=("مدیرعامل", "رئیس هیئت‌مدیره")).exists()
    )
    return {
        "is_staff": is_staff,
        "is_employee": is_employee,
        "can_manage_staff": can_manage_staff,
    }


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPRequestThrottle])
def request_otp(request):
    serializer = RequestOTPSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    result = serializer.save()
    return Response(
        {
            "success": True,
            "message": "کد تایید ارسال شد.",
            **result,
        }
    )


@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([OTPVerifyThrottle])
def verify_otp(request):

    serializer = VerifyOTPSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    token, _ = Token.objects.get_or_create(user=user)
    profile = getattr(user, "profile", None)
    return Response(
        {
            "success": True,
            "token": token.key,
            "user": {
                "id": user.id,
                "mobile": profile.mobile if profile else None,
                **_staff_flags(user),
            },
        }
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me(request):
    user = request.user
    profile = getattr(user, "profile", None)
    return Response(
        {
            "id": user.id,
            "mobile": profile.mobile if profile else None,
            **_staff_flags(user),
        }
    )

@api_view(["GET", "PATCH"])
@permission_classes([IsAuthenticated])
def profile(request):
    user_profile = getattr(request.user, "profile", None)

    if user_profile is None:
        return Response(
            {"detail": "پروفایل کاربر یافت نشد."},
            status=404,
        )

    if request.method == "GET":
        serializer = ProfileSerializer(user_profile)
        return Response(serializer.data)

    serializer = ProfileSerializer(
        user_profile,
        data=request.data,
        partial=True,
    )
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def logout(request):
    if hasattr(request.user, "auth_token"):
        request.user.auth_token.delete()
    return Response({"success": True})
