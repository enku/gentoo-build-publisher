"""GBP System cache

This here is the "global" systems cache for Gentoo Build Publisher. It supports the
CacheProtocol interface.
"""

from typing import Any

from django.core.cache import cache as django_cache

STATS_KEY = "gbp-stats"  # Cache key for storing/retrieving Stats
_NOT_SET = object()


class GBPSiteCache:
    """The site-wide cache (class) for Gentoo Build Publisher"""

    DEFAULT_PREFIX = "gbp-"

    def __init__(self, prefix: str = DEFAULT_PREFIX) -> None:
        object.__setattr__(self, "_cache", django_cache)
        object.__setattr__(self, "_prefix", prefix)

    def __setattr__(self, key: str, value: Any) -> None:
        """Assign the given cache key the given value"""
        if key.startswith("_"):
            raise ValueError('Values must not being with "_"')

        self._cache.set(f"{self._prefix}{key}", value, timeout=None)

    def __getattr__(self, key: str) -> Any:
        """Return the value in the cache given the key

        If the key does not exist in the cache, return the default.
        """
        value = self._cache.get(f"{self._prefix}{key}", _NOT_SET)

        if value is _NOT_SET:
            raise AttributeError(key)

        return value

    def __delattr__(self, key: str) -> None:
        """Delete the value associated with the given key.

        Silently ignore non-existent keys.
        """
        self._cache.delete(f"{self._prefix}{key}")

    def __contains__(self, key: str) -> bool:
        return key in self._cache


def clear(cache_: GBPSiteCache) -> None:
    """Clear the cache

    Note: this clears all the underlying cache and not just the keys starting with
    the prefix.
    """
    cache_._cache.clear()  # pylint: disable=protected-access


cache = GBPSiteCache()
