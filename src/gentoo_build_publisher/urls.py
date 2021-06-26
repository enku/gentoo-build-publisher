"""Default urlconf for gentoo_build_publisher"""
from django.contrib import admin
from django.urls import path

from gentoo_build_publisher import views

urlpatterns = [
    path("", views.index, name="index"),
    path("publish/<build_name>/<int:build_number>/", views.publish, name="publish"),
    path("pull/<build_name>/<int:build_number>/", views.pull, name="pull"),
    path("delete/<build_name>/<int:build_number>/", views.delete, name="delete"),
    path("latest/<build_name>/", views.latest, name="latest"),
    path("builds/<build_name>/", views.list_builds, name="list_builds"),
    path("build/<build_name>/<int:build_number>/", views.show_build, name="show_build"),
    path("logs/<build_name>/<int:build_number>/", views.logs, name="logs"),
    path("diff/<build_name>/<int:left>/<int:right>/", views.diff_builds, name="diff"),
    path("machines/", views.list_machines, name="list_machines"),
    path("admin/", admin.site.urls),
]
