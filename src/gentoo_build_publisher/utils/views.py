"""Functions/data to support the dashboard view"""
from __future__ import annotations

import datetime as dt
import itertools
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, NamedTuple, TypeAlias, TypedDict

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


class DashboardContext(TypedDict):
    """Definition for the Dashboard context"""

    # Days of the week
    bot_days: list[str]

    # Total # of builds
    build_count: int

    # Builds not yet completed
    builds_to_do: list[BuildRecord]

    # Each machine gets it's own #rrggbb color
    gradient_colors: Gradient

    machine_dist: list[int]
    machines: list[str]
    now: dt.datetime

    # Total number of packages for all machines
    package_count: int

    # list of packages for a build, key is the str(build)
    build_packages: dict[str, list[str]]

    # set of latest_packages that are published
    latest_published: set[BuildRecord]

    # recently built packages (for all machines)
    recent_packages: dict[str, set[str]]

    # Each machine's total package size
    total_package_size: dict[str, int]

    # List of the latest builds for each machine, if the machine has one
    latest_builds: list[BuildRecord]

    # List of builds from the last 24 hours
    built_recently: list[BuildRecord]

    builds_over_time: list[list[int]]

    # Total count machines with unpublished latest builds
    unpublished_builds_count: int


class MachineContext(TypedDict):
    """machine view context"""

    bot_days: list[str]
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
    return [datetime.strftime(fmt) for datetime in get_bot_days(start, days)]


def create_dashboard_context(input_context: ViewInputContext) -> DashboardContext:
    """Initialize and return DashboardContext"""
    publisher = input_context.publisher
    bot_days = get_bot_days(input_context.now, input_context.days)
    machines = publisher.machines()
    machines.sort(key=lambda machine: machine.build_count, reverse=True)
    context: DashboardContext = {
        "bot_days": days_strings(input_context.now, input_context.days),
        "build_count": 0,
        "builds_to_do": [],
        "build_packages": {},
        "builds_over_time": [],
        "built_recently": [],
        "latest_builds": [],
        "latest_published": set(),
        "gradient_colors": gradient_colors(*input_context.color_range, len(machines)),
        "machine_dist": [machine.build_count for machine in machines],
        "machines": [machine.machine for machine in machines],
        "now": input_context.now,
        "package_count": 0,
        "recent_packages": {},
        "total_package_size": {machine.machine: 0 for machine in machines},
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
            context["builds_to_do"].append(record)

        context = add_package_metadata(record, context, publisher, input_context.cache)

        assert record.submitted is not None

        if (day_submitted := record.submitted.astimezone().date()) >= bot_days[0]:
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
    context["builds_over_time"] = bot_to_list(builds_over_time)

    return context


@dataclass(frozen=True, kw_only=True)
class MachineInputContext(ViewInputContext):
    """ViewInputContext for the machine view"""

    machine: str


def create_machine_context(input_context: MachineInputContext) -> MachineContext:
    """Return context for the machine view"""
    machine = input_context.machine
    bot_days = get_bot_days(input_context.now, input_context.days)
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
        if (day_submitted := build.submitted.astimezone().date()) >= bot_days[0]:
            builds_over_time[day_submitted][machine] += 1

    return {
        "bot_days": days_strings(input_context.now, input_context.days),
        "build_count": machine_info.build_count,
        "builds": machine_info.builds,
        "builds_over_time": bot_to_list(builds_over_time),
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
    """Update `context` with `package_count` and `total_package_size`"""
    context = context.copy()
    metadata = get_metadata(record, publisher, cache)

    if metadata and record.completed:
        context["package_count"] += metadata.packages.total
        context["total_package_size"][record.machine] += metadata.packages.size

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
        context["total_package_size"][record.machine] += sum(i.size for i in packages)

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


def bot_to_list(
    builds_over_time: Mapping[dt.date, Mapping[MachineName, int]],
) -> list[list[int]]:
    """Return builds_over_time dict of lists into a list of lists

    Each list is a list for each machine in `machines`
    """
    list_of_lists = []
    days = [*builds_over_time.keys()]
    days.sort()

    if not days:
        return []

    machines = [*builds_over_time[days[0]].keys()]

    for machine in machines:
        tally = []

        for day in days:
            tally.append(builds_over_time[day][machine])
        list_of_lists.append(tally)

    return list_of_lists


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

    return sorted(packages, key=lambda package: package.build_time, reverse=True)[:10]


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
    bot: dict[dt.date, dict[str, int]] = {}

    for day in get_bot_days(start, days):
        days_builds = bot[day] = {}

        for machine in machines:
            days_builds[machine] = 0

    return bot


def gradient_colors(start: Color, stop: Color, size: int) -> list[str]:
    """Return a list of size color strings (#rrggbb) as a gradient from start to stop"""
    return gradient(start, stop, size)


def gradient(start: Color, end: Color, count: int) -> Gradient:
    """Return gradient from start to end with count colors"""
    return [str(color) for color in Color.gradient(start, end, count)]


def get_bot_days(start: dt.datetime, days: int) -> list[dt.date]:
    """Return initial builds over time (all 0s for the given start date and days"""
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
