"""Tests for gentoo_build_publisher.urls"""

# pylint: disable=missing-docstring
from unittest import TestCase

from gentoo_build_publisher import plugins, urls
from gentoo_build_publisher.django.gentoo_build_publisher.urls import urlpatterns


class PluginURLPatterns(TestCase):
    def test(self) -> None:
        plugin = plugins.Plugin(
            name="test",
            app="test",
            version="1.0",
            description="A test app",
            graphql=None,
            urls="gentoo_build_publisher.django.gentoo_build_publisher.urls",
        )
        self.assertEqual(urls.plugin_urlpatterns(plugin), urlpatterns)

    def test_none(self) -> None:
        plugin = plugins.Plugin(
            name="test",
            app="test",
            version="1.0",
            description="A test app",
            graphql=None,
            urls=None,
        )
        self.assertEqual(urls.plugin_urlpatterns(plugin), [])

    def test_plugin_without_django_app(self) -> None:
        plugin = plugins.Plugin(
            name="test",
            app=None,
            version="1.0",
            description="A test app",
            graphql=None,
            urls=None,
        )
        self.assertEqual(urls.plugin_urlpatterns(plugin), [])
