
from django.urls import path

from . import views


urlpatterns = [
    path("provinces/", views.list_provinces, name="provinces"),
    path("cities/", views.list_cities, name="cities"),
]
