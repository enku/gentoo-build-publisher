"""GBP System cache

This here is the "global" systems cache for Gentoo Build Publisher. It supports the
CacheProtocol interface.
"""

from typing import Any

from django.core.cache import cache as django_cache


class GBPSiteCache:
    """The site-wide cache (class) for Gentoo Build Publisher"""

    DEFAULT_PREFIX = "gbp-"

    def __init__(self, prefix: str = DEFAULT_PREFIX) -> None:
        self._cache = django_cache
        self.prefix = prefix

    def set(self, key: str, value: Any) -> None:
        """Assign the given cache key the given value"""
        self._cache.set(f"{self.prefix}{key}", value, timeout=None)

    def get(self, key: str, default: Any = None) -> Any:
        """Return the value in the cache given the key

        If the key does not exist in the cache, return the default.
        """
        return self._cache.get(f"{self.prefix}{key}", default)

    def delete(self, key: str) -> None:
        """Delete the value associated with the given key.

        Silently ignore non-existent keys.
        """
        self._cache.delete(f"{self.prefix}{key}")

    def clear(self) -> None:
        """Clear the cache

        Note: this clears all the underlying cache and not just the keys starting with
        the prefix.
        """
        self._cache.clear()


cache = GBPSiteCache()
