import json

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth.models import Group, User
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.serializers import ChoiceField, Serializer


EXECUTIVE_GROUPS = ("مدیرعامل", "رئیس هیئت‌مدیره")
STAFF_ROLE_NAMES = (
    "مدیرعامل",
    "رئیس هیئت‌مدیره",
    "مدیر داخلی",
    "حسابدار",
    "مشاور",
    "مشتری",
)


class StaffRoleSerializer(Serializer):
    role = ChoiceField(choices=tuple((name, name) for name in STAFF_ROLE_NAMES))


def can_manage_staff(user):
    return bool(
        user.is_authenticated
        and (
            user.is_superuser
            or user.groups.filter(name__in=EXECUTIVE_GROUPS).exists()
        )
    )


def _forbidden():
    return Response(
        {"detail": "فقط مدیرعامل یا رئیس هیئت‌مدیره مجاز به مدیریت نقش کارکنان هستند."},
        status=status.HTTP_403_FORBIDDEN,
    )


def _user_role_data(user):
    profile = getattr(user, "profile", None)
    roles = list(
        user.groups.filter(name__in=STAFF_ROLE_NAMES)
        .order_by("name")
        .values_list("name", flat=True)
    )
    return {
        "id": user.pk,
        "mobile": profile.mobile if profile else None,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "full_name": " ".join(part for part in (user.first_name, user.last_name) if part).strip(),
        "roles": roles,
        "role": roles[0] if len(roles) == 1 else ("بدون نقش" if not roles else "چند نقش"),
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "date_joined": user.date_joined,
    }


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_list(request):
    if not can_manage_staff(request.user):
        return _forbidden()

    queryset = User.objects.select_related("profile").prefetch_related("groups").order_by("-date_joined", "-pk")
    search = request.query_params.get("search", "").strip()
    if search:
        queryset = queryset.filter(
            Q(username__icontains=search)
            | Q(first_name__icontains=search)
            | Q(last_name__icontains=search)
            | Q(profile__mobile__icontains=search)
        ).distinct()

    try:
        page = max(1, int(request.query_params.get("page", "1")))
    except (TypeError, ValueError):
        page = 1
    page_size = 25
    count = queryset.count()
    users = queryset[(page - 1) * page_size : page * page_size]
    return Response({
        "count": count,
        "page": page,
        "page_size": page_size,
        "results": [_user_role_data(user) for user in users],
    })


@api_view(["PATCH"])
@permission_classes([IsAuthenticated])
def assign_staff_role(request, user_id):
    if not can_manage_staff(request.user):
        return _forbidden()

    serializer = StaffRoleSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    role_name = serializer.validated_data["role"]

    with transaction.atomic():
        try:
            target = User.objects.select_for_update().get(pk=user_id)
        except User.DoesNotExist:
            return Response({"detail": "کاربر موردنظر یافت نشد."}, status=status.HTTP_404_NOT_FOUND)

        if target.pk == request.user.pk:
            return Response(
                {"detail": "برای جلوگیری از قطع دسترسی مدیریتی، تغییر نقش حساب خودتان از این صفحه مجاز نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if target.is_superuser:
            return Response(
                {"detail": "نقش حساب‌های دارای دسترسی سیستمی از این بخش قابل تغییر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        selected_group = Group.objects.filter(name=role_name).first()
        if selected_group is None:
            return Response(
                {"detail": "گروه‌های استاندارد ساخته نشده‌اند. ابتدا فرمان setup_staff_roles را اجرا کنید."},
                status=status.HTTP_409_CONFLICT,
            )

        previous_roles = list(
            target.groups.filter(name__in=STAFF_ROLE_NAMES)
            .order_by("name")
            .values_list("name", flat=True)
        )
        if previous_roles == [role_name]:
            return Response({"success": True, "changed": False, "user": _user_role_data(target)})

        existing_groups = list(target.groups.filter(name__in=STAFF_ROLE_NAMES))
        if existing_groups:
            target.groups.remove(*existing_groups)
        target.groups.add(selected_group)

        content_type = ContentType.objects.get_for_model(User)
        LogEntry.objects.create(
            user=request.user,
            content_type=content_type,
            object_id=str(target.pk),
            object_repr=str(target),
            action_flag=CHANGE,
            change_message=json.dumps({
                "event": "staff_role_changed",
                "previous_roles": previous_roles,
                "new_role": role_name,
                "target_user_id": target.pk,
            }, ensure_ascii=False),
        )

    target.refresh_from_db()
    return Response({"success": True, "changed": True, "user": _user_role_data(target)})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def staff_role_history(request):
    if not can_manage_staff(request.user):
        return _forbidden()

    content_type = ContentType.objects.get_for_model(User)
    entries = LogEntry.objects.filter(
        content_type=content_type,
        action_flag=CHANGE,
        change_message__contains='"event": "staff_role_changed"',
    ).select_related("user__profile").order_by("-action_time")[:50]

    entries = list(entries)
    target_ids = [entry.object_id for entry in entries if str(entry.object_id).isdigit()]
    target_users = {
        str(user.pk): user
        for user in User.objects.filter(pk__in=target_ids).select_related("profile")
    }

    def display_user(user):
        if user is None:
            return ""
        full_name = user.get_full_name().strip()
        if full_name:
            return full_name
        profile = getattr(user, "profile", None)
        if profile and profile.mobile:
            return profile.mobile
        return user.username

    results = []
    for entry in entries:
        try:
            details = json.loads(entry.change_message)
        except (TypeError, ValueError):
            continue
        if details.get("event") != "staff_role_changed":
            continue
        target_user = target_users.get(str(entry.object_id))
        results.append({
            "id": entry.pk,
            "actor": display_user(entry.user) or entry.user.username,
            "target": display_user(target_user) or entry.object_repr,
            "previous_roles": details.get("previous_roles", []),
            "new_role": details.get("new_role"),
            "created_at": entry.action_time,
        })
    return Response(results)
