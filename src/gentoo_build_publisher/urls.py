"""Default urlconf for gentoo_build_publisher"""
from ariadne.contrib.django.views import GraphQLView
from django.contrib import admin
from django.urls import path

from gentoo_build_publisher import views
from gentoo_build_publisher.graphql import schema

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
    path("graphql", GraphQLView.as_view(schema=schema), name="graphql"),
]
