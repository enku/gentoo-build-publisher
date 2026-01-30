"""GBP System cache

This here is the "global" systems cache for Gentoo Build Publisher. It supports the
CacheProtocol interface.
"""

from typing import Any, Self

from django.core.cache import cache as django_cache

ATTR_DELIM = ":"
CACHE_DELIM = "/"


class GBPSiteCache:
    """The site-wide cache (class) for Gentoo Build Publisher"""

    DEFAULT_PREFIX = "gbp"

    def __init__(self, prefix: str = DEFAULT_PREFIX) -> None:
        self._prefix = prefix
        self._timeout: float | None = None

    def set(self, key: str, value: Any) -> None:
        """Assign the given cache key the given value"""
        if key.startswith("_"):
            raise ValueError('Values must not begin with "_"')
        if CACHE_DELIM in key:
            raise ValueError(f"Values must not contain {CACHE_DELIM!r}")

        django_cache.set(self._get_key(key), value, timeout=self._timeout)

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value in the cache given the key

        If the key does not exist in the cache, return the default.
        """
        return django_cache.get(self._get_key(key), default)

    def delete(self, key: str) -> None:
        """Delete the value associated with the given key.

        Silently ignore non-existent keys.
        """
        django_cache.delete(self._get_key(key))

    def contains(self, key: str) -> bool:
        """Tell whether the cache contains the given key"""
        return self._get_key(key) in django_cache

    def __truediv__(self, prefix: str) -> Self:
        """Return the sub-cache

        The sub-cache is a cache whose prefix with the parent prefix prepended to the
        given prefix.
        """
        return type(self)(prefix=f"{self._prefix}/{prefix}")

    def set_timeout(self, seconds: int | None) -> None:
        """Set the (sub) cache item timeout"""
        self._timeout = seconds

    def _get_key(self, key: str) -> str:
        return f"{self._prefix}{ATTR_DELIM}{key}"


def clear() -> None:
    """Clear the cache

    Note: this clears all the underlying cache and not just the keys starting with
    the prefix.
    """
    django_cache.clear()


cache = GBPSiteCache()
