"""Functions/data to support the dashboard view"""
import datetime as dt
import itertools
from dataclasses import astuple, dataclass
from typing import Mapping, TypedDict

from gentoo_build_publisher.publisher import BuildPublisher, MachineInfo
from gentoo_build_publisher.types import (
    Build,
    BuildLike,
    BuildRecord,
    CacheProtocol,
    GBPMetadata,
    Package,
)
from gentoo_build_publisher.utils import Color, lapsed

BuildID = str
CPV = str
MachineName = str

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
    machine_colors: list[str]

    machine_dist: list[int]
    machines: list[str]
    now: dt.datetime

    # Total number of packages for all machines
    package_count: int

    # list of packages for a build, key is the str(build)
    build_packages: dict[str, list[str]]

    # set of latest_packages that are published
    latest_published: set[Build]

    # recently built packages (for all machines)
    recent_packages: dict[str, set[str]]

    # Each machine's total package size
    total_package_size: dict[str, int]

    # List of the latest builds for each machine, if the machine has one
    latest_builds: list[Build]

    # List of builds from the last 24 hours
    built_recently: list[Build]

    builds_over_time: list[list[int]]

    # Total count machines with unpublished latest builds
    unpublished_builds_count: int


@dataclass
class BuildSummary:
    """Struct returned by get_build_summary()"""

    latest_builds: list[BuildRecord]
    built_recently: list[BuildRecord]
    build_packages: dict[BuildID, list[CPV]]
    latest_published: set[BuildRecord]


def create_dashboard_context(  # pylint: disable=too-many-arguments
    start: dt.datetime,
    days: int,
    tzinfo: dt.tzinfo,
    color_range: tuple[Color, Color],
    publisher: BuildPublisher,
    cache: CacheProtocol,
) -> DashboardContext:
    """Initialize and return DashboardContext"""
    bot_days: list[dt.date] = [
        start.date() - dt.timedelta(days=d) for d in range(days - 1, -1, -1)
    ]
    color_start, color_end = color_range
    machines = publisher.machines()
    machines.sort(key=lambda m: m.build_count, reverse=True)
    context: DashboardContext = {
        "bot_days": [datetime.strftime("%A") for datetime in bot_days],
        "build_count": 0,
        "builds_to_do": [],
        "build_packages": {},
        "builds_over_time": [],
        "built_recently": [],
        "latest_builds": [],
        "latest_published": set(),
        "machine_colors": [
            str(color)
            for color in Color.gradient(color_start, color_end, len(machines))
        ],
        "machine_dist": [machine.build_count for machine in machines],
        "machines": [machine.machine for machine in machines],
        "now": start,
        "package_count": 0,
        "recent_packages": {},
        "total_package_size": {machine.machine: 0 for machine in machines},
        "unpublished_builds_count": 0,
    }
    records = itertools.chain(
        *(publisher.records.for_machine(machine.machine) for machine in machines)
    )
    builds_over_time = create_builds_over_time(bot_days, [m.machine for m in machines])
    for record in records:
        context["build_count"] += 1
        if not record.completed:
            context["builds_to_do"].append(record)

        context = add_package_metadata(record, context, publisher, cache)

        assert record.submitted is not None

        day_submitted = record.submitted.astimezone(tzinfo).date()
        if day_submitted >= bot_days[0]:
            builds_over_time[day_submitted][record.machine] += 1

    (
        context["latest_builds"],
        context["built_recently"],
        context["build_packages"],
        context["latest_published"],
    ) = astuple(get_build_summary(start, machines, publisher, cache))
    context["unpublished_builds_count"] = len(
        [build for build in context["latest_builds"] if not publisher.published(build)]
    )
    context["builds_over_time"] = bot_to_list(builds_over_time)

    return context


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

        if record.submitted and lapsed(record.submitted, context["now"]) < 86400:
            for package in metadata.packages.built:
                if package.cpv in context["recent_packages"]:
                    context["recent_packages"][package.cpv].add(record.machine)
                elif len(context["recent_packages"]) < 12:
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

        if lapsed(record.completed, now) < 86400:
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
    build: BuildLike, publisher: BuildPublisher, cache: CacheProtocol
) -> GBPMetadata | None:
    """Return the GBPMetadata for a package.

    This call may be cashed for performance.
    """
    cache_key = f"metadata-{build}"
    cached = cache.get(cache_key, _NOT_FOUND)

    if cached is _NOT_FOUND:
        try:
            metadata = publisher.storage.get_metadata(build)

            if metadata:
                cache.set(cache_key, metadata)

            return metadata
        except LookupError:
            return None

    metadata = cached
    return metadata


def get_packages(
    build: BuildLike, publisher: BuildPublisher, cache: CacheProtocol
) -> list[Package]:
    """Return a list of packages from a build by looking up the index.

    This call may be cached for performance.
    """
    cache_key = f"packages-{build}"
    cached = cache.get(cache_key, _NOT_FOUND)

    if cached is _NOT_FOUND:
        try:
            packages = publisher.get_packages(build)
        except LookupError:
            packages = []

        cache.set(cache_key, packages)
    else:
        packages = cached

    return packages


def create_builds_over_time(
    days: list[dt.date], machines: list[MachineName]
) -> dict[dt.date, dict[str, int]]:
    """Return an "empty" builds_over_time dict given the days and machines

    All the machines for all the days will have 0 builds.
    """
    bot: dict[dt.date, dict[str, int]] = {}

    for day in days:
        days_builds = bot[day] = {}

        for machine in machines:
            days_builds[machine] = 0

    return bot