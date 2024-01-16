"""Functions/data to support the dashboard view"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, TypeAlias, TypedDict

from django.http import HttpRequest
from django.utils import timezone

from gentoo_build_publisher.common import Build, CacheProtocol, GBPMetadata, Package
from gentoo_build_publisher.publisher import BuildPublisher, MachineInfo
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.utils.time import lapsed

BuildID: TypeAlias = str  # pylint: disable=invalid-name
CPV: TypeAlias = str  # pylint: disable=invalid-name
Gradient: TypeAlias = list[str]
MachineName: TypeAlias = str


MAX_DISPLAYED_PKGS = 12
SECONDS_PER_DAY = 86400
_NOT_FOUND = object()


class StatsCollector:
    """Interface to collect statistics about the Publisher"""

    def __init__(self, publisher: BuildPublisher, cache: CacheProtocol) -> None:
        self.publisher = publisher
        self.cache = cache
        self._machine_info = {mi.machine: mi for mi in publisher.machines()}

    def machine_info(self, machine: MachineName) -> MachineInfo:
        """Return the MachineInfo object for the given machine"""
        return self._machine_info.get(machine, MachineInfo(machine))

    def machine_infos(self) -> list[MachineInfo]:
        """Return the MachineInfo instance for each machine with builds"""
        return list(self._machine_info.values())

    @property
    @lru_cache
    def machines(self) -> list[MachineName]:
        """Returns a list of machines with builds

        Machines are orderd by build count (descending), then machine name (ascending)
        """
        return sorted(
            self._machine_info,
            key=lambda machine: (-1 * self._machine_info[machine].build_count, machine),
        )

    @lru_cache
    def package_count(self, machine: MachineName) -> int:
        """Return the total number of completed builds for the given machine"""
        if not (mi := self.machine_info(machine)):
            return 0

        total = 0
        for build in mi.builds:
            metadata = get_metadata(build, self.publisher, self.cache)
            if metadata and build.completed:
                total += metadata.packages.total

        return total

    def build_packages(self, build: Build) -> list[str]:
        """Return a list of CPVs build in the given build"""
        metadata = get_metadata(build, self.publisher, self.cache)
        return [i.cpv for i in metadata.packages.built] if metadata is not None else []

    def latest_build(self, machine: MachineName) -> BuildRecord | None:
        """Return the latest build for the given machine

        If the Machine has no builds, return None.
        """
        if not ((mi := self.machine_info(machine)) and (build := mi.latest_build)):
            return None

        return build

    def latest_published(self, machine: MachineName) -> BuildRecord | None:
        """Return the latest build for the given machine if that build is published

        Otherwise return None.
        """
        if not (
            (latest := self.latest_build(machine))
            and (mi := self.machine_info(machine))
            and (published := mi.published_build)
        ):
            return None

        return latest if latest == self.publisher.record(published) else None

    def recent_packages(self, machine: MachineName, maximum: int = 10) -> list[Package]:
        """Return the list of recent packages for a machine (up to maximum)"""
        if not (mi := self.machine_info(machine)):
            return []

        packages: set[Package] = set()
        for build in mi.builds:
            if not (metadata := get_metadata(build, self.publisher, self.cache)):
                continue
            packages.update(metadata.packages.built)
            if len(packages) >= maximum:
                break

        return sorted(packages, key=lambda p: p.build_time, reverse=True)[:maximum]

    def total_package_size(self, machine: MachineName) -> int:
        """Return the total size (bytes) of all packages in all builds for machine"""
        if not (mi := self.machine_info(machine)):
            return 0

        total = 0
        for record in mi.builds:
            if record.completed and (
                metadata := get_metadata(record, self.publisher, self.cache)
            ):
                total += metadata.packages.size

        return total

    def built_recently(self, build: BuildRecord, now: dt.datetime) -> bool:
        """Return True if the given build was built within 24 hours of the given time"""
        return False if not build.built else lapsed(build.built, now) < SECONDS_PER_DAY

    def builds_by_day(self, machine: MachineName) -> dict[dt.date, int]:
        """Return a dict of count of builds by day for the given machine"""
        if not (mi := self.machine_info(machine)):
            return {}

        bbd: dict[dt.date, int] = {}
        for build in mi.builds:
            if not build.submitted:
                continue
            date = build.submitted.date()
            bbd[date] = bbd.setdefault(date, 0) + 1

        return bbd


class DashboardContext(TypedDict):
    """Definition for the Dashboard context"""

    chart_days: list[str]
    build_count: int
    builds_not_completed: list[BuildRecord]
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

    chart_days: list[str]
    build_count: int
    builds: list[BuildRecord]
    builds_over_time: list[list[int]]
    gradient_colors: Gradient
    latest_build: BuildRecord
    machine: str
    machines: list[str]
    published_build: Build | None
    recent_packages: list[Package]
    storage: int


@dataclass(frozen=True, kw_only=True)
class ViewInputContext:
    """Input context to generate output context"""

    days: int
    color_range: tuple[Color, Color]
    publisher: BuildPublisher
    cache: CacheProtocol
    now: dt.datetime = field(default_factory=timezone.localtime)


def days_strings(start: dt.datetime, days: int) -> list[str]:
    """Return list of datetimes from start as strings"""
    fmt = "%A" if days <= 7 else "%x"
    return [datetime.strftime(fmt) for datetime in get_chart_days(start, days)]


def create_dashboard_context(input_context: ViewInputContext) -> DashboardContext:
    """Initialize and return DashboardContext"""
    publisher = input_context.publisher
    sc = StatsCollector(publisher, input_context.cache)
    chart_days = get_chart_days(input_context.now, input_context.days)

    recent_packages: dict[str, set[MachineName]] = {}
    for machine in sc.machines:
        if record := sc.latest_build(machine):
            for package in sc.build_packages(record):
                if len(recent_packages) < MAX_DISPLAYED_PKGS:
                    recent_packages.setdefault(package, set()).add(machine)

    context: DashboardContext = {
        "chart_days": days_strings(input_context.now, input_context.days),
        "build_count": sum(
            machine_info.build_count for machine_info in sc.machine_infos()
        ),
        "builds_not_completed": [
            build
            for machine_info in sc.machine_infos()
            for build in machine_info.builds
            if not build.completed
        ],
        "build_packages": {
            latest.id: sc.build_packages(latest)
            for machine in sc.machines
            if (latest := sc.latest_build(machine))
        },
        "builds_over_time": [
            [sc.builds_by_day(machine).get(day, 0) for day in chart_days]
            for machine in sc.machines
        ],
        "built_recently": [
            latest
            for machine in sc.machines
            if (latest := sc.latest_build(machine))
            and latest.completed
            and lapsed(latest.completed, input_context.now) < SECONDS_PER_DAY
        ],
        "latest_builds": [
            build for machine in sc.machines if (build := sc.latest_build(machine))
        ],
        "latest_published": set(
            lp for machine in sc.machines if (lp := sc.latest_published(machine))
        ),
        "gradient_colors": gradient_colors(
            *input_context.color_range, len(sc.machines)
        ),
        "builds_per_machine": [
            sc.machine_info(machine).build_count for machine in sc.machines
        ],
        "machines": sc.machines,
        "now": input_context.now,
        "package_count": sum(sc.package_count(machine) for machine in sc.machines),
        "recent_packages": recent_packages,
        "total_package_size_per_machine": {
            machine: sc.total_package_size(machine) for machine in sc.machines
        },
        "unpublished_builds_count": sum(
            not publisher.published(build)
            for machine in sc.machines
            if (build := sc.latest_build(machine))
        ),
    }

    return context


@dataclass(frozen=True, kw_only=True)
class MachineInputContext(ViewInputContext):
    """ViewInputContext for the machine view"""

    machine: str


def create_machine_context(input_context: MachineInputContext) -> MachineContext:
    """Return context for the machine view"""
    sc = StatsCollector(input_context.publisher, input_context.cache)
    chart_days = get_chart_days(input_context.now, input_context.days)
    machine = input_context.machine
    machine_info = sc.machine_info(machine)
    assert (latest_build := sc.latest_build(machine))

    return {
        "chart_days": days_strings(input_context.now, input_context.days),
        "build_count": machine_info.build_count,
        "builds": machine_info.builds,
        "builds_over_time": [
            [sc.builds_by_day(machine).get(day, 0) for day in chart_days]
        ],
        "gradient_colors": gradient_colors(*input_context.color_range, 10),
        "latest_build": latest_build,
        "machine": machine,
        "machines": [machine],
        "published_build": machine_info.published_build,
        "recent_packages": sc.recent_packages(machine),
        "storage": sc.total_package_size(machine),
    }


def get_metadata(
    build: Build, publisher: BuildPublisher, cache: CacheProtocol
) -> GBPMetadata | None:
    """Return the GBPMetadata for a package.

    This call may be cashed for performance.
    """
    cache_key = f"metadata-{build}"

    if (cached := cache.get(cache_key, _NOT_FOUND)) is _NOT_FOUND:
        try:
            metadata = publisher.storage.get_metadata(build)
        except LookupError:
            return None

        if metadata:
            cache.set(cache_key, metadata)

        return metadata

    metadata = cached
    return metadata


def gradient_colors(start: Color, stop: Color, size: int) -> list[str]:
    """Return a list of size color strings (#rrggbb) as a gradient from start to stop"""
    return gradient(start, stop, size)


def gradient(start: Color, end: Color, count: int) -> Gradient:
    """Return gradient from start to end with count colors"""
    return [str(color) for color in Color.gradient(start, end, count)]


def get_chart_days(start: dt.datetime, days: int) -> list[dt.date]:
    """Return initial chart data (all 0s for the given start date and days"""
    return [start.date() - dt.timedelta(days=d) for d in range(days - 1, -1, -1)]


def get_query_value_from_request(
    request: HttpRequest, key: str, type_: type, fallback: int
) -> Any:
    """Return given query value from the query params"""
    if (query_value := request.GET.get(key, _NOT_FOUND)) == _NOT_FOUND:
        return fallback
    try:
        return type_(query_value)
    except ValueError:
        return fallback
