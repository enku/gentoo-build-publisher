"""GBP System cache

This here is the "global" systems cache for Gentoo Build Publisher. It supports the
CacheProtocol interface.
"""

from typing import Any, Self

from django.core.cache import cache as django_cache

_NOT_SET = object()


class GBPSiteCache:
    """The site-wide cache (class) for Gentoo Build Publisher"""

    DEFAULT_PREFIX = "gbp"

    def __init__(self, prefix: str = DEFAULT_PREFIX) -> None:
        object.__setattr__(self, "_cache", django_cache)
        object.__setattr__(self, "_prefix", prefix)
        set_timeout(self, None)

    def __setattr__(self, key: str, value: Any) -> None:
        """Assign the given cache key the given value"""
        if key.startswith("_"):
            raise ValueError('Values must not being with "_"')
        if "/" in key:
            raise ValueError('Values must not contain "/"')

        self._cache.set(f"{self._prefix}.{key}", value, timeout=self._timeout)

    def __getattr__(self, key: str) -> Any:
        """Return the value in the cache given the key

        If the key does not exist in the cache, return the default.
        """
        value = self._cache.get(f"{self._prefix}.{key}", _NOT_SET)

        if value is _NOT_SET:
            raise AttributeError(key)

        return value

    def __delattr__(self, key: str) -> None:
        """Delete the value associated with the given key.

        Silently ignore non-existent keys.
        """
        self._cache.delete(f"{self._prefix}.{key}")

    def __contains__(self, key: str) -> bool:
        return f"{self._prefix}.{key}" in self._cache

    def __truediv__(self, prefix: str) -> Self:
        """Return the sub-cache

        The sub-cache is a cache whose prefix with the parent prefix prepended to the
        given prefix.
        """
        return type(self)(prefix=f"{self._prefix}/{prefix}")


def clear(cache_: GBPSiteCache) -> None:
    """Clear the cache

    Note: this clears all the underlying cache and not just the keys starting with
    the prefix.
    """
    cache_._cache.clear()  # pylint: disable=protected-access


def set_timeout(cache_: GBPSiteCache, seconds: int | None) -> None:
    """Set the (sub) cache item timeout"""
    object.__setattr__(cache_, "_timeout", seconds)


cache = GBPSiteCache()
