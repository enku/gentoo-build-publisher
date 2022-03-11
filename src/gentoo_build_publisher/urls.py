"""Default urlconf for gentoo_build_publisher"""
from ariadne_django.views import GraphQLView
from django.contrib import admin
from django.urls import path

from gentoo_build_publisher import views
from gentoo_build_publisher.graphql import schema

urlpatterns = [
    path("", views.dashboard),
    path("admin/", admin.site.urls),
    path("graphql", GraphQLView.as_view(schema=schema), name="graphql"),
]
