"""Default urlconf for gentoo_build_publisher"""
from django.contrib import admin
from django.urls import path

from gentoo_build_publisher import views

urlpatterns = [
    path("publish/<build_name>/<int:build_number>/", views.publish, name="publish"),
    path('admin/', admin.site.urls),
]
