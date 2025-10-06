"""GBP View Context Utilities"""

import datetime as dt
from dataclasses import dataclass, field
from typing import TypedDict, cast

from django.core.cache import cache as django_cache
from django.utils import timezone

from gentoo_build_publisher import plugins, publisher
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.stats import Stats
from gentoo_build_publisher.types import Build, CacheProtocol, Package
from gentoo_build_publisher.utils.time import SECONDS_PER_DAY, lapsed

from .utils import (
    Gradient,
    color_range_from_settings,
    days_strings,
    get_chart_days,
    gradient_colors,
)

MAX_DISPLAYED_PKGS = 12
STATS_KEY = "gbp-stats"  # Cache key for storing/retrieving Stats


class DashboardContext(TypedDict):
    """Definition for the Dashboard context"""

    chart_days: list[str]
    build_count: int
    gradient_colors: Gradient
    builds_per_machine: list[int]
    machines: list[str]
    now: dt.datetime
    package_count: int
    build_packages: dict[str, list[str]]
    latest_published: set[BuildRecord]
    recent_packages: dict[str, set[str]]
    total_package_size_per_machine: dict[str, int]
    latest_builds: list[BuildRecord]
    built_recently: list[BuildRecord]
    builds_over_time: list[list[int]]
    unpublished_builds_count: int


class MachineContext(TypedDict):
    """machine view context"""

    average_storage: float
    build_count: int
    builds: list[BuildRecord]
    builds_over_time: list[list[int]]
    chart_days: list[str]
    gradient_colors: Gradient
    latest_build: BuildRecord
    machine: str
    machines: list[str]
    packages_built_today: list[Package]
    published_build: Build | None
    recent_packages: list[Package]
    storage: int


class BuildContext(TypedDict):
    """build view context"""

    build: BuildRecord
    machine: str
    build_id: str
    gradient_colors: Gradient
    packages_built: list[Package]
    published: bool
    tags: list[str]


class AboutContext(TypedDict):
    """Context for the about view"""

    gradient_colors: Gradient
    plugins: list[plugins.Plugin]


@dataclass(frozen=True, kw_only=True)
class ViewInputContext:
    """Input context to generate output context"""

    days: int
    cache: CacheProtocol = field(default_factory=lambda: django_cache)
    now: dt.datetime = field(default_factory=timezone.localtime)


def create_dashboard_context(input_context: ViewInputContext) -> DashboardContext:
    """Initialize and return DashboardContext"""
    stats = get_stats(input_context.cache)
    chart_days = get_chart_days(input_context.now, input_context.days)

    recent_packages: dict[str, set[str]] = {}
    for machine in stats.machines:
        if record := stats.latest_build[machine]:
            for package in stats.build_packages[record]:
                if len(recent_packages) < MAX_DISPLAYED_PKGS:
                    recent_packages.setdefault(package, set()).add(machine)

    return {
        "chart_days": days_strings(input_context.now, input_context.days),
        "build_count": sum(stats.machine_info[m].build_count for m in stats.machines),
        "build_packages": {
            latest.id: stats.build_packages[latest]
            for machine in stats.machines
            if (latest := stats.latest_build[machine])
        },
        "builds_over_time": [
            [stats.builds_by_day[machine].get(day, 0) for day in chart_days]
            for machine in stats.machines
        ],
        "built_recently": [
            latest
            for machine in stats.machines
            if (latest := stats.latest_build[machine])
            and latest.completed
            and lapsed(latest.completed, input_context.now) < SECONDS_PER_DAY
        ],
        "latest_builds": [
            build
            for machine in stats.machines
            if (build := stats.latest_build[machine])
        ],
        "latest_published": set(
            lp for machine in stats.machines if (lp := stats.latest_published[machine])
        ),
        "gradient_colors": gradient_colors(
            *color_range_from_settings(), len(stats.machines)
        ),
        "builds_per_machine": [
            stats.machine_info[machine].build_count for machine in stats.machines
        ],
        "machines": stats.machines,
        "now": input_context.now,
        "package_count": sum(
            stats.package_counts[machine] for machine in stats.machines
        ),
        "recent_packages": recent_packages,
        "total_package_size_per_machine": {
            machine: stats.total_package_size[machine] for machine in stats.machines
        },
        "unpublished_builds_count": sum(
            not publisher.published(build)
            for machine in stats.machines
            if (build := stats.latest_build[machine])
        ),
    }


@dataclass(frozen=True, kw_only=True)
class MachineInputContext(ViewInputContext):
    """ViewInputContext for the machine view"""

    machine: str


def create_machine_context(input_context: MachineInputContext) -> MachineContext:
    """Return context for the machine view"""
    stats = get_stats(input_context.cache)
    now = input_context.now
    chart_days = get_chart_days(now, input_context.days)
    machine = input_context.machine
    machine_info = stats.machine_info[machine]
    latest_build = stats.latest_build[machine]
    storage = stats.total_package_size[machine]

    assert latest_build

    return {
        "average_storage": storage / machine_info.build_count,
        "chart_days": days_strings(now, input_context.days),
        "build_count": machine_info.build_count,
        "builds": machine_info.builds,
        "builds_over_time": [
            [stats.builds_by_day[machine].get(day, 0) for day in chart_days]
        ],
        "gradient_colors": gradient_colors(*color_range_from_settings(), 10),
        "latest_build": latest_build,
        "machine": machine,
        "machines": [machine],
        "packages_built_today": stats.packages_by_day[machine].get(now.date(), []),
        "published_build": machine_info.published_build,
        "recent_packages": stats.recent_packages[machine],
        "storage": storage,
    }


@dataclass(frozen=True, kw_only=True)
class BuildInputContext:
    """ViewInputContext for the build view"""

    build: BuildRecord


def create_build_context(input_context: BuildInputContext) -> BuildContext:
    """Return context for the build view"""
    build = input_context.build
    packages_built = publisher.build_metadata(build).packages.built

    return {
        "build": build,
        "build_id": build.build_id,
        "gradient_colors": gradient_colors(*color_range_from_settings(), 10),
        "machine": build.machine,
        "packages_built": packages_built,
        "published": publisher.published(build),
        "tags": publisher.tags(build),
    }


def create_about_context() -> AboutContext:
    """Return AboutContext for the plugins view"""
    return {
        "gradient_colors": gradient_colors(*color_range_from_settings(), 2),
        "plugins": plugins.get_plugins(),
    }


def get_stats(cache: CacheProtocol) -> Stats:
    """Get the GBP Stats

    Check the cache and if the value is cached return the cached value.
    Otherwise collect the Stats and store it in the cache.
    """
    if stats := cache.get(STATS_KEY, None):
        return cast(Stats, stats)

    stats = Stats.collect()
    cache.set(STATS_KEY, stats)
    return stats
