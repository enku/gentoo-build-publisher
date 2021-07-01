"""Default urlconf for gentoo_build_publisher"""
from django.contrib import admin
from django.urls import path

from gentoo_build_publisher import views

urlpatterns = [
    path("api/builds/<build_name>/", views.list_builds),
    path("api/builds/<build_name>/<int:build_number>", views.api_build),
    path("api/builds/<build_name>/<int:build_number>/log", views.logs),
    path("api/builds/<build_name>/<int:build_number>/publish", views.publish),
    path("api/builds/<build_name>/diff/<int:left>/<int:right>", views.diff_builds),
    path("api/builds/<build_name>/latest", views.latest),
    path("api/machines/", views.list_machines),
    path("", views.index),
    path("admin/", admin.site.urls),
]
