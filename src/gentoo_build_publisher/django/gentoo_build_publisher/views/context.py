"""Template Context

GBP Django views with the @render decorator return a template context type. This is a
dataclass that is first converted to a dict (non-recursively) and then passed to the
template target given to @render.

The purpose of the template context dataclasses is to serve as a type-hinted, documented
template context.

Each template context dataclass has a create() classmethod that takes zero or more
keyword arguments and returns the template context. These the kwargs are input variables
for which the create() method uses to instantiate the template context instance.
Typically these input variables are extracted from the Django request, but .create()
shouldn't be passed the request object itself.
"""

import datetime as dt
from dataclasses import dataclass
from typing import Self

from django.utils import timezone

from gentoo_build_publisher import plugins, publisher
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.stats import Stats
from gentoo_build_publisher.types import Build, MachineNotFoundError, Package
from gentoo_build_publisher.utils.time import SECONDS_PER_DAY, lapsed

from .utils import (
    Gradient,
    color_range_from_settings,
    days_strings,
    get_chart_days,
    gradient_colors,
)

MAX_DISPLAYED_PKGS = 12


# pylint: disable=too-many-instance-attributes
@dataclass(kw_only=True, frozen=True)
class Dashboard:
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

    @classmethod
    def create(cls, *, days: int, now: dt.datetime | None = None) -> Self:
        """Create a template context given the input variables"""
        now = now or timezone.localtime()
        stats = Stats.with_cache()
        chart_days = get_chart_days(now, days)

        recent_packages: dict[str, set[str]] = {}
        for machine in stats.machines:
            if record := stats.latest_build[machine]:
                for package in stats.build_packages[record]:
                    if len(recent_packages) < MAX_DISPLAYED_PKGS:
                        recent_packages.setdefault(package, set()).add(machine)

        return cls(
            chart_days=days_strings(now, days),
            build_count=sum(stats.machine_info[m].build_count for m in stats.machines),
            build_packages={
                latest.id: stats.build_packages[latest]
                for machine in stats.machines
                if (latest := stats.latest_build[machine])
            },
            builds_over_time=[
                [stats.builds_by_day[machine].get(day, 0) for day in chart_days]
                for machine in stats.machines
            ],
            built_recently=[
                latest
                for machine in stats.machines
                if (latest := stats.latest_build[machine])
                and latest.completed
                and lapsed(latest.completed, now) < SECONDS_PER_DAY
            ],
            latest_builds=[
                build
                for machine in stats.machines
                if (build := stats.latest_build[machine])
            ],
            latest_published=set(
                lp
                for machine in stats.machines
                if (lp := stats.latest_published[machine])
            ),
            gradient_colors=gradient_colors(
                *color_range_from_settings(), len(stats.machines)
            ),
            builds_per_machine=[
                stats.machine_info[machine].build_count for machine in stats.machines
            ],
            machines=stats.machines,
            now=now,
            package_count=sum(
                stats.package_counts[machine] for machine in stats.machines
            ),
            recent_packages=recent_packages,
            total_package_size_per_machine={
                machine: stats.total_package_size[machine] for machine in stats.machines
            },
            unpublished_builds_count=sum(
                not publisher.published(build)
                for machine in stats.machines
                if (build := stats.latest_build[machine])
            ),
        )


@dataclass(kw_only=True, frozen=True)
class Machine:  # pylint: disable=too-many-instance-attributes
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
    days: int

    @classmethod
    def create(cls, *, machine: str, days: int, now: dt.datetime | None = None) -> Self:
        """Create a template context given the input variables"""
        now = now or timezone.localtime()
        stats = Stats.with_cache()
        chart_days = get_chart_days(now, days)

        if (machine_info := stats.machine_info.get(machine)) is None:
            raise MachineNotFoundError(machine)

        latest_build = stats.latest_build[machine]
        storage = stats.total_package_size[machine]

        assert latest_build

        return cls(
            days=days,
            average_storage=storage / machine_info.build_count,
            chart_days=days_strings(now, days),
            build_count=machine_info.build_count,
            builds=machine_info.builds,
            builds_over_time=[
                [stats.builds_by_day[machine].get(day, 0) for day in chart_days]
            ],
            gradient_colors=gradient_colors(*color_range_from_settings(), 10),
            latest_build=latest_build,
            machine=machine,
            machines=[machine],
            packages_built_today=stats.packages_by_day[machine].get(now.date(), []),
            published_build=machine_info.published_build,
            recent_packages=stats.recent_packages[machine],
            storage=storage,
        )


@dataclass(kw_only=True, frozen=True)
class BuildView:
    """build view context"""

    build: BuildRecord
    machine: str
    build_id: str
    gradient_colors: Gradient
    packages_built: list[Package]
    total_package_size: int
    published: bool
    tags: list[str]

    @classmethod
    def create(cls, *, build: BuildRecord) -> Self:
        """Create a template context given the input variables"""
        packages_built = publisher.build_metadata(build).packages.built

        return cls(
            build=build,
            build_id=build.build_id,
            gradient_colors=gradient_colors(*color_range_from_settings(), 10),
            machine=build.machine,
            packages_built=packages_built,
            total_package_size=sum(p.size for p in packages_built),
            published=publisher.published(build),
            tags=publisher.tags(build),
        )


@dataclass(kw_only=True, frozen=True)
class Logs:
    """gbp-logs-fancy context"""

    build: BuildRecord
    gradient_colors: Gradient

    @classmethod
    def create(cls, *, build: BuildRecord) -> Self:
        """Create a template context given the input variables"""
        return cls(
            build=build,
            gradient_colors=gradient_colors(*color_range_from_settings(), 10),
        )


@dataclass(kw_only=True, frozen=True)
class About:
    """Context for the about view"""

    gradient_colors: Gradient
    plugins: list[plugins.Plugin]

    @classmethod
    def create(cls) -> Self:
        """Create a template context given the input variables"""
        return cls(
            gradient_colors=gradient_colors(*color_range_from_settings(), 2),
            plugins=plugins.get_plugins(),
        )


@dataclass(frozen=True, kw_only=True)
class ReposDotConf:
    """The repos.conf view template context"""

    dirname: str
    hostname: str
    repos: set[str]

    @classmethod
    def create(cls, *, dirname: str, hostname: str, repos: set[str]) -> Self:
        """Create a template context given the input variables"""
        return cls(dirname=dirname, hostname=hostname, repos=repos)


@dataclass(kw_only=True, frozen=True)
class BinReposDotConf:
    """Context for the binrepos.conf view"""

    machine: str
    uri: str

    @classmethod
    def create(cls, *, machine: str, uri: str) -> Self:
        """Create a template context given the input variables"""
        return cls(machine=machine, uri=uri)
