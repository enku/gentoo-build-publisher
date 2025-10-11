"""Tests for the GBP site cache"""

# pylint: disable=missing-docstring

from unittest import TestCase

from django.core.cache import cache as django_cache
from unittest_fixtures import Fixtures, given

from gentoo_build_publisher.cache import GBPSiteCache, clear


@given(clear_cache=lambda _: django_cache.clear())
class GBPSiteCacheTests(TestCase):
    # pylint: disable=protected-access,unused-argument
    def test_set(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test")

        cache.foo = "bar"

        self.assertEqual(cache.foo, "bar")
        self.assertEqual(cache._cache.get("test.foo"), "bar")

    def test_get(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test")
        cache._cache.set("test.foo", "bar")

        self.assertEqual(cache.foo, "bar")

    def test_delete(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test")
        cache._cache.set("test.foo", "bar")

        del cache.foo

        self.assertNotIn("foo", cache)
        self.assertEqual(cache._cache.get("test.foo"), None)

    def test_clear(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test")

        cache._cache.set("test.foo", "bar")
        cache._cache.set("bar", "baz")

        clear(cache)

        self.assertNotIn("foo", cache)
        self.assertEqual(cache._cache.get("test.foo"), None)
        self.assertEqual(cache._cache.get("bar"), None)

    def test_subcache(self, fixtures: Fixtures) -> None:
        root = GBPSiteCache(prefix="root")
        sub = root / "sub"

        sub.foo = "bar"

        self.assertEqual(sub.foo, "bar")
        self.assertEqual(root._cache.get("root/sub.foo"), "bar")
        self.assertEqual((root / "sub").foo, "bar")

        subsub = sub / "sub"

        subsub.bar = "baz"

        self.assertEqual(subsub.bar, "baz")
        self.assertEqual(root._cache.get("root/sub/sub.bar"), "baz")

    def test_cache_key_with_slash_not_allowed(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test")

        with self.assertRaises(ValueError) as context:
            setattr(cache, "/foo", "bar")

        self.assertEqual(str(context.exception), 'Values must not contain "/"')
