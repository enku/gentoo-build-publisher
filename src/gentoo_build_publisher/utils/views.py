"""Functions/data to support the dashboard view"""
from __future__ import annotations

import datetime as dt
import itertools
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, NamedTuple, TypeAlias, TypedDict

from django.http import HttpRequest
from django.utils import timezone

from gentoo_build_publisher.common import Build, CacheProtocol, GBPMetadata, Package
from gentoo_build_publisher.publisher import BuildPublisher, MachineInfo
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.utils import (
    Color,
    dict_of_dicts_to_list_of_lists,
    dict_of_values,
)
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

        Machines are ordered by build count (descending), then machine name (ascending)
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
    chart_days = get_chart_days(input_context.now, input_context.days)
    machines = publisher.machines()
    machines.sort(key=lambda machine: machine.build_count, reverse=True)
    context: DashboardContext = {
        "chart_days": days_strings(input_context.now, input_context.days),
        "build_count": 0,
        "builds_not_completed": [],
        "build_packages": {},
        "builds_over_time": [],
        "built_recently": [],
        "latest_builds": [],
        "latest_published": set(),
        "gradient_colors": gradient_colors(*input_context.color_range, len(machines)),
        "builds_per_machine": [machine.build_count for machine in machines],
        "machines": [machine.machine for machine in machines],
        "now": input_context.now,
        "package_count": 0,
        "recent_packages": {},
        "total_package_size_per_machine": {machine.machine: 0 for machine in machines},
        "unpublished_builds_count": 0,
    }
    records = itertools.chain(
        *(publisher.records.for_machine(machine.machine) for machine in machines)
    )
    builds_over_time = create_builds_over_time(
        input_context.now, input_context.days, [m.machine for m in machines]
    )
    for record in records:
        context["build_count"] += 1
        if not record.completed:
            context["builds_not_completed"].append(record)

        context = add_package_metadata(record, context, publisher, input_context.cache)

        assert record.submitted is not None

        if (day_submitted := record.submitted.astimezone().date()) >= chart_days[0]:
            builds_over_time[day_submitted][record.machine] += 1

    (
        context["latest_builds"],
        context["built_recently"],
        context["build_packages"],
        context["latest_published"],
    ) = get_build_summary(input_context.now, machines, publisher, input_context.cache)
    context["unpublished_builds_count"] = len(
        [build for build in context["latest_builds"] if not publisher.published(build)]
    )
    context["builds_over_time"] = dict_of_dicts_to_list_of_lists(builds_over_time)

    return context


@dataclass(frozen=True, kw_only=True)
class MachineInputContext(ViewInputContext):
    """ViewInputContext for the machine view"""

    machine: str


def create_machine_context(input_context: MachineInputContext) -> MachineContext:
    """Return context for the machine view"""
    machine = input_context.machine
    chart_days = get_chart_days(input_context.now, input_context.days)
    builds_over_time = create_builds_over_time(
        input_context.now, input_context.days, [machine]
    )
    machine_info = MachineInfo(machine)
    assert machine_info.latest_build
    storage = 0
    recent_packages = get_machine_recent_packages(
        machine_info, input_context.publisher, input_context.cache
    )

    for build in machine_info.builds:
        metadata = get_metadata(build, input_context.publisher, input_context.cache)
        if metadata and build.completed:
            storage += metadata.packages.size
        assert build.submitted is not None
        if (day_submitted := build.submitted.astimezone().date()) >= chart_days[0]:
            builds_over_time[day_submitted][machine] += 1

    return {
        "chart_days": days_strings(input_context.now, input_context.days),
        "build_count": machine_info.build_count,
        "builds": machine_info.builds,
        "builds_over_time": dict_of_dicts_to_list_of_lists(builds_over_time),
        "gradient_colors": gradient_colors(*input_context.color_range, 10),
        "latest_build": machine_info.latest_build,
        "machine": machine,
        "machines": [machine],
        "published_build": machine_info.published_build,
        "recent_packages": recent_packages,
        "storage": storage,
    }


class BuildSummary(NamedTuple):
    """Struct returned by get_build_summary()"""

    latest_builds: list[BuildRecord]
    built_recently: list[BuildRecord]
    build_packages: dict[BuildID, list[CPV]]
    latest_published: set[BuildRecord]


def add_package_metadata(
    record: BuildRecord,
    context: DashboardContext,
    publisher: BuildPublisher,
    cache: CacheProtocol,
) -> DashboardContext:
    """Update `context` with `package_count` and `total_package_size_per_machine`"""
    context = context.copy()
    metadata = get_metadata(record, publisher, cache)

    if metadata and record.completed:
        context["package_count"] += metadata.packages.total
        context["total_package_size_per_machine"][
            record.machine
        ] += metadata.packages.size

        if (
            record.submitted
            and lapsed(record.submitted, context["now"]) < SECONDS_PER_DAY
        ):
            for package in metadata.packages.built:
                if package.cpv in context["recent_packages"]:
                    context["recent_packages"][package.cpv].add(record.machine)
                elif len(context["recent_packages"]) < MAX_DISPLAYED_PKGS:
                    context["recent_packages"][package.cpv] = {record.machine}
    else:
        packages = get_packages(record, publisher, cache)
        context["package_count"] += len(packages)
        context["total_package_size_per_machine"][record.machine] += sum(
            i.size for i in packages
        )

    return context


def get_build_summary(
    now: dt.datetime,
    machines: list[MachineInfo],
    publisher: BuildPublisher,
    cache: CacheProtocol,
) -> BuildSummary:
    """Update `context` with `latest_builds` and `build_recently`"""
    latest_builds = []
    built_recently = []
    build_packages = {}
    latest_published = set()

    for machine in machines:
        if not (latest_build := machine.latest_build):
            continue

        if publisher.published(latest_build):
            latest_published.add(latest_build)

        record = publisher.record(latest_build)

        latest_builds.append(latest_build)
        build_id = latest_build.id
        metadata = get_metadata(latest_build, publisher, cache)
        build_packages[build_id] = (
            [i.cpv for i in metadata.packages.built] if metadata is not None else []
        )

        assert record.completed, record

        if lapsed(record.completed, now) < SECONDS_PER_DAY:
            built_recently.append(latest_build)

    return BuildSummary(latest_builds, built_recently, build_packages, latest_published)


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


def get_machine_recent_packages(
    machine_info: MachineInfo,
    publisher: BuildPublisher,
    cache: CacheProtocol,
    max_count: int = 10,
) -> list[Package]:
    """Return the list of recent packages for a machine (up to max_count)"""
    packages: set[Package] = set()
    for build in machine_info.builds:
        metadata = get_metadata(build, publisher, cache)
        if not metadata:
            continue
        packages.update(metadata.packages.built)
        if len(packages) >= max_count:
            break

    return sorted(packages, key=lambda package: package.build_time, reverse=True)[
        :max_count
    ]


def get_packages(
    build: Build, publisher: BuildPublisher, cache: CacheProtocol
) -> list[Package]:
    """Return a list of packages from a build by looking up the index.

    This call may be cached for performance.
    """
    cache_key = f"packages-{build}"

    if (cached := cache.get(cache_key, _NOT_FOUND)) is _NOT_FOUND:
        try:
            packages = publisher.get_packages(build)
        except LookupError:
            packages = []

        cache.set(cache_key, packages)
    else:
        packages = cached

    return packages


def create_builds_over_time(
    start: dt.datetime, days: int, machines: list[MachineName]
) -> dict[dt.date, dict[str, int]]:
    """Return an "empty" builds_over_time dict given the days and machines

    All the machines for all the days will have 0 builds.
    """
    return dict_of_values(
        get_chart_days(start, days), lambda: dict_of_values(machines, int)
    )


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
