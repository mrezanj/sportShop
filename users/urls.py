from django.urls import path
from . import views
from . import staff_views

urlpatterns = [
    path("request-otp/", views.request_otp, name="request-otp"),
    path("verify-otp/", views.verify_otp, name="verify-otp"),
    path("me/", views.me, name="me"),
    path("profile/", views.profile, name="profile"),
    path("logout/", views.logout, name="logout"),
    path("staff/", staff_views.staff_list, name="staff-list"),
    path("staff/history/", staff_views.staff_role_history, name="staff-role-history"),
    path("staff/<int:user_id>/role/", staff_views.assign_staff_role, name="staff-role-assignment"),
    path("staff/<int:user_id>/revoke-superuser/", staff_views.revoke_superuser_access, name="staff-revoke-superuser"),
]
