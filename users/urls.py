from django.urls import path
from . import views

urlpatterns = [
    path('request-otp/', views.request_otp, name='request-otp'),
    path('verify-otp/', views.verify_otp, name='verify-otp'),
    path('me/', views.me, name='me'),
    path('logout/', views.logout, name='logout'),
]