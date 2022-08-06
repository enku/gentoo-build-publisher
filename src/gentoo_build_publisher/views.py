"""Django views for Gentoo Build Publisher"""
from __future__ import annotations

import datetime as dt
import itertools
from collections import defaultdict
from dataclasses import astuple, dataclass
from typing import Mapping, Optional, TypedDict

from django.conf import settings
from django.core.cache import cache
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from gentoo_build_publisher.publisher import MachineInfo, get_publisher
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.types import Build, GBPMetadata, Package
from gentoo_build_publisher.utils import Color, lapsed

GBP_SETTINGS = getattr(settings, "BUILD_PUBLISHER", {})

gradient = Color.gradient


class DashboardContext(TypedDict):
    """Definition for the Dashboard context"""

    # Days of the week
    bot_days: list[str]

    # Total # of builds
    build_count: int

    # Builds not yet completed
    builds_to_do: list[Build]

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
    recent_packages: defaultdict[str, set[str]]

    # Each machine's total package size
    total_package_size: defaultdict[str, int]

    # List of the latest builds for each machine, if the machine has one
    latest_builds: list[Build]

    # List of builds from the last 24 hours
    built_recently: list[Build]

    builds_over_time: list[list[int]]

    # Total count machines with unpublished latest builds
    unpublished_builds_count: int


BuildID = str
CPV = str
MachineName = str


@dataclass
class BuildSummary:
    """Struct returned by get_build_summary()"""

    latest_builds: list[BuildRecord]
    built_recently: list[BuildRecord]
    build_packages: dict[BuildID, list[CPV]]
    latest_published: set[BuildRecord]


def get_packages(build: Build) -> list[Package]:
    """Return a list of packages from a build by looking up the index.

    This call may be cached for performance.
    """
    publisher = get_publisher()
    cache_key = f"packages-{build}"

    cached = cache.get(cache_key, None)

    if cached is not None:
        packages: list[Package] = cached
    else:
        try:
            packages = publisher.get_packages(build)
        except LookupError:
            packages = []

        cache.set(cache_key, packages)

    return packages


def bot_to_list(
    builds_over_time: Mapping[dt.date, Mapping[MachineName, int]],
    machines: list[MachineInfo],
    days: list[dt.date],
) -> list[list[int]]:
    """Return builds_over_time dict of lists into a list of lists

    Each list is a list for each machine in `machines`
    """
    list_of_lists = []
    for machine in machines:
        tally = []

        for day in days:
            tally.append(builds_over_time[day][machine.machine])
        list_of_lists.append(tally)

    return list_of_lists


def get_build_summary(now: dt.datetime, machines: list[MachineInfo]) -> BuildSummary:
    """Update `context` with `latest_builds` and `build_recently`"""
    latest_builds = []
    built_recently = []
    build_packages = {}
    latest_published = set()
    publisher = get_publisher()

    for machine in machines:
        if not (latest_build := machine.latest_build):
            continue

        if publisher.published(latest_build):
            latest_published.add(latest_build)

        record = publisher.record(latest_build)
        if not record.completed:
            continue

        latest_builds.append(latest_build)
        build_id = latest_build.id
        try:
            build_packages[build_id] = [
                i.cpv
                for i in publisher.storage.get_metadata(latest_build).packages.built
            ]
        except LookupError:
            build_packages[build_id] = []

        if lapsed(record.completed, now) < 86400:
            built_recently.append(latest_build)

    return BuildSummary(latest_builds, built_recently, build_packages, latest_published)


def package_metadata(record: BuildRecord, context: DashboardContext) -> None:
    """Update `context` with `package_count` and `total_package_size`"""
    metadata: Optional[GBPMetadata]
    publisher = get_publisher()

    try:
        metadata = publisher.storage.get_metadata(record)
    except LookupError:
        metadata = None

    if metadata and record.completed:
        context["package_count"] += metadata.packages.total
        context["total_package_size"][record.machine] += metadata.packages.size

        if record.submitted and lapsed(record.submitted, context["now"]) < 86400:
            for package in metadata.packages.built:
                if (
                    package.cpv in context["recent_packages"]
                    or len(context["recent_packages"]) < 12
                ):
                    context["recent_packages"][package.cpv].add(record.machine)
    else:
        packages = get_packages(record)
        context["package_count"] += len(packages)
        context["total_package_size"][record.machine] += sum(i.size for i in packages)


def dashboard(request: HttpRequest) -> HttpResponse:
    """Dashboard view"""
    publisher = get_publisher()
    now = timezone.localtime()
    current_timezone = timezone.get_current_timezone()
    bot_days: list[dt.date] = [
        now.date() - dt.timedelta(days=days) for days in range(6, -1, -1)
    ]
    builds_over_time: dict[dt.date, defaultdict[str, int]] = {
        day: defaultdict(int) for day in bot_days
    }
    machines = publisher.machines()
    records = itertools.chain(
        *(publisher.records.for_machine(machine.machine) for machine in machines)
    )
    machines.sort(key=lambda m: m.build_count, reverse=True)
    color_start = Color(*GBP_SETTINGS.get("COLOR_START", (80, 69, 117)))
    color_end = Color(*GBP_SETTINGS.get("COLOR_END", (221, 218, 236)))
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
            str(color) for color in gradient(color_start, color_end, len(machines))
        ],
        "machine_dist": [machine.build_count for machine in machines],
        "machines": [machine.machine for machine in machines],
        "now": now,
        "package_count": 0,
        "recent_packages": defaultdict(set),
        "total_package_size": defaultdict(int),
        "unpublished_builds_count": 0,
    }

    for record in records:
        context["build_count"] += 1
        if not record.completed:
            context["builds_to_do"].append(record)

        package_metadata(record, context)

        if record.submitted is None:
            continue

        day_submitted = record.submitted.astimezone(current_timezone).date()
        if day_submitted >= bot_days[0]:
            builds_over_time[day_submitted][record.machine] += 1

    (
        context["latest_builds"],
        context["built_recently"],
        context["build_packages"],
        context["latest_published"],
    ) = astuple(get_build_summary(now, machines))
    context["unpublished_builds_count"] = len(
        [build for build in context["latest_builds"] if not publisher.published(build)]
    )
    context["builds_over_time"] = bot_to_list(builds_over_time, machines, bot_days)

    # https://stackoverflow.com/questions/4764110/django-template-cant-loop-defaultdict
    context["recent_packages"].default_factory = None

    return render(request, "gentoo_build_publisher/dashboard.html", context)


def repos_dot_conf(request: HttpRequest, machine: str) -> HttpResponse:
    """Create a repos.conf entry for the given machine"""
    if not (build := MachineInfo(machine).published_build):
        raise Http404("Published build for that machine does not exist")

    context = {
        "hostname": request.headers.get("Host", "localhost").partition(":")[0],
        "machine": machine,
        "repos": get_publisher().storage.repos(build),
    }
    return render(
        request, "gentoo_build_publisher/repos.conf", context, content_type="text/plain"
    )


def binrepos_dot_conf(request: HttpRequest, machine: str) -> HttpResponse:
    """Create a binrepos.conf entry for the given machine"""
    if not MachineInfo(machine).published_build:
        raise Http404("Published build for that machine does not exist")

    context = {"uri": request.build_absolute_uri(f"/binpkgs/{machine}/")}
    return render(
        request,
        "gentoo_build_publisher/binrepos.conf",
        context,
        content_type="text/plain",
    )
