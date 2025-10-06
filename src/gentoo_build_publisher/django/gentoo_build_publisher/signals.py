"""Signal handlers for Gentoo Build Publisher's Django app"""

from typing import Any

from gentoo_build_publisher import worker
from gentoo_build_publisher.signals import dispatcher


def update_stats_cache() -> None:
    """Update the stats cache"""
    # pylint: disable=import-outside-toplevel
    from django.core.cache import cache

    from gentoo_build_publisher.django.gentoo_build_publisher.views.context import (
        STATS_KEY,
    )
    from gentoo_build_publisher.stats import Stats

    stats = Stats.collect()
    cache.set(STATS_KEY, stats, timeout=None)


def background_update_stats_cache(**_kwargs: Any) -> None:
    """Run update_stats_cache in the background"""
    worker.run(update_stats_cache)


def init() -> None:
    """Bind signal handlers with the dispatcher"""
    dispatcher.bind(
        postdelete=background_update_stats_cache,
        postpull=background_update_stats_cache,
        published=background_update_stats_cache,
        tagged=background_update_stats_cache,
        untagged=background_update_stats_cache,
    )
