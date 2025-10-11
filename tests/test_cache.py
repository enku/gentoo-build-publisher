"""Tests for the GBP site cache"""

# pylint: disable=missing-docstring

from unittest import TestCase, mock

from django.core.cache import cache as django_cache
from unittest_fixtures import Fixtures, given

from gentoo_build_publisher.cache import GBPSiteCache, clear, set_timeout


@given(clear_cache=lambda _: django_cache.clear())
class GBPSiteCacheTests(TestCase):
    # pylint: disable=protected-access,unused-argument
    def test_set(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test")

        cache.foo = "bar"

        self.assertEqual(cache.foo, "bar")
        self.assertEqual(django_cache.get("test.foo"), "bar")

    def test_get(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test")
        django_cache.set("test.foo", "bar")

        self.assertEqual(cache.foo, "bar")

    def test_delete(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test")
        django_cache.set("test.foo", "bar")

        del cache.foo

        self.assertNotIn("foo", cache)
        self.assertEqual(django_cache.get("test.foo"), None)

    def test_clear(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test")

        django_cache.set("test.foo", "bar")
        django_cache.set("bar", "baz")

        clear()

        self.assertNotIn("foo", cache)
        self.assertEqual(django_cache.get("test.foo"), None)
        self.assertEqual(django_cache.get("bar"), None)

    def test_subcache(self, fixtures: Fixtures) -> None:
        root = GBPSiteCache(prefix="root")
        sub = root / "sub"

        sub.foo = "bar"

        self.assertEqual(sub.foo, "bar")
        self.assertEqual(django_cache.get("root/sub.foo"), "bar")
        self.assertEqual((root / "sub").foo, "bar")

        subsub = sub / "sub"

        subsub.bar = "baz"

        self.assertEqual(subsub.bar, "baz")
        self.assertEqual(django_cache.get("root/sub/sub.bar"), "baz")

    def test_contains(self, fixtures: Fixtures) -> None:
        root = GBPSiteCache(prefix="root")
        sub = root / "sub"

        root.foo = "bar"
        sub.baz = "bar"

        self.assertTrue("foo" in root)
        self.assertFalse("baz" in root)
        self.assertTrue("baz" in sub)
        self.assertFalse("foo" in sub)

    def test_cache_key_with_slash_not_allowed(self, fixtures: Fixtures) -> None:
        cache = GBPSiteCache(prefix="test")

        with self.assertRaises(ValueError) as context:
            setattr(cache, "/foo", "bar")

        self.assertEqual(str(context.exception), 'Values must not contain "/"')

    def test_with_timeout(self, fixtures: Fixtures) -> None:
        root = GBPSiteCache(prefix="test")
        sub = root / "sub"
        set_timeout(sub, 300)

        with mock.patch.object(django_cache, "set") as cache_set:
            sub.key = 1
            cache_set.assert_called_with("test/sub.key", 1, timeout=300)

            root.key = 2
            cache_set.assert_called_with("test.key", 2, timeout=None)
