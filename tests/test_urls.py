"""Tests for gentoo_build_publisher.urls"""

# pylint: disable=missing-docstring

from unittest import TestCase

from gentoo_build_publisher import plugins, urls

urlpatterns = ["this", "is", "a", "test"]


class PluginURLPatternsTests(TestCase):
    def test_no_urls(self) -> None:
        plugin = plugins.Plugin(
            name="Test URLS", app="tests.test_urls", graphql=None, urls=None
        )
        self.assertEqual([], urls.plugin_urlpatterns(plugin))

    def test_importerror(self) -> None:
        plugin = plugins.Plugin(
            name="Test URLS", app="tests.test_urls", graphql=None, urls="tests.bogus"
        )
        self.assertEqual([], urls.plugin_urlpatterns(plugin))

    def test(self) -> None:
        plugin = plugins.Plugin(
            name="Test URLS",
            app="tests.test_urls",
            graphql=None,
            urls="tests.test_urls",
        )
        self.assertEqual(urlpatterns, urls.plugin_urlpatterns(plugin))
