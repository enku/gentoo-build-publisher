"""Tests for the GBP site cache"""

# pylint: disable=missing-docstring

from unittest import TestCase

from django.core.cache import cache as django_cache
from unittest_fixtures import Fixtures, given

from gentoo_build_publisher.cache import GBPSiteCache


@given(clear_cache=lambda _: django_cache.clear())
class GBPSiteCacheTests(TestCase):
    # pylint: disable=protected-access,unused-argument
    def test_set(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test-")

        cache.set("foo", "bar")

        self.assertEqual(cache.get("foo"), "bar")
        self.assertEqual(cache._cache.get("test-foo"), "bar")

    def test_get(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test-")
        cache._cache.set("test-foo", "bar")

        self.assertEqual(cache.get("foo"), "bar")

    def test_get_with_default(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test-")

        self.assertEqual(cache.get("foo", "baz"), "baz")

    def test_delete(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test-")
        cache._cache.set("test-foo", "bar")

        cache.delete("foo")

        self.assertIs(cache.get("foo"), None)
        self.assertEqual(cache._cache.get("test-foo"), None)

    def test_clear(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test-")

        cache._cache.set("test-foo", "bar")
        cache._cache.set("bar", "baz")

        cache.clear()

        self.assertIs(cache.get("foo"), None)
        self.assertEqual(cache._cache.get("test-foo"), None)
        self.assertEqual(cache._cache.get("bar"), None)
