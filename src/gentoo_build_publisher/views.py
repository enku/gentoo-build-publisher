"""Django views for Gentoo Build Publisher"""
import datetime as dt
from collections import defaultdict
from typing import Optional, TypedDict

from django.conf import settings
from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from gentoo_build_publisher.build import GBPMetadata, Package
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import BuildMan, MachineInfo
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
    builds_to_do: list[BuildMan]

    # Each machine gets it's own #rrggbb color
    machine_colors: list[str]

    machine_dist: list[int]
    machines: list[str]
    now: dt.datetime

    # Total number of packages for all machines
    package_count: int

    # list of packages for a build, key is the str(build)
    build_packages: dict[str, list[str]]

    # recently built packages (for all machines)
    recent_packages: defaultdict[str, set]

    # Each machine's total package size
    total_package_size: defaultdict[str, int]

    # List of the latest builds for each machine, if the machine has one
    latest_builds: list[BuildMan]

    # List of builds from the last 24 hours
    built_recently: list[BuildMan]

    builds_over_time: list[list[int]]

    # Total count machines with unpublished latest builds
    unpublished_builds_count: int


def get_packages(build: BuildMan) -> list[Package]:
    """Return a list of packages from a build by looking up the index.

    This call may be cached for performance.
    """
    cache_key = f"packages-{build.name}-{build.number}"

    try:
        return cache.get_or_set(cache_key, build.get_packages, timeout=None)
    except LookupError:
        return []


def bot_to_list(builds_over_time, machines, days):
    """Return builds_over_time dict of lists into a list of lists

    Each list is a list for each machine in `machines`
    """
    list_of_lists = []
    for machine in machines:
        tally = []

        for day in days:
            tally.append(builds_over_time[day][machine.name])
        list_of_lists.append(tally)

    return list_of_lists


def get_build_summary(now: dt.datetime, machines: list[MachineInfo]):
    """Update `context` with `latest_builds` and `build_recently`"""
    latest_builds = []
    built_recently = []
    build_packages = {}

    for machine in machines:
        if not (latest_build := machine.latest_build):
            continue

        if not latest_build.db.completed:
            continue

        latest_builds.append(latest_build)
        build_id = str(latest_build)
        try:
            build_packages[build_id] = [
                i.cpv
                for i in latest_build.storage.get_metadata(
                    latest_build.build.id
                ).packages.built
            ]
        except LookupError:
            build_packages[build_id] = []

        if lapsed(latest_build.db.completed, now) < 86400:
            built_recently.append(latest_build)

    return latest_builds, built_recently, build_packages


def package_metadata(buildman: BuildMan, context: DashboardContext):
    """Update `context` with `package_count` and `total_package_size`"""
    metadata: Optional[GBPMetadata]

    try:
        metadata = buildman.storage.get_metadata(buildman.build.id)
    except LookupError:
        metadata = None

    if metadata:
        context["package_count"] += metadata.packages.total
        context["total_package_size"][buildman.name] += metadata.packages.size

        if lapsed(buildman.db.submitted, context["now"]) < 86400:
            for package in metadata.packages.built:
                if (
                    package.cpv in context["recent_packages"]
                    or len(context["recent_packages"]) < 12
                ):
                    context["recent_packages"][package.cpv].add(buildman.name)
    else:
        packages = get_packages(buildman)
        context["package_count"] += len(packages)
        context["total_package_size"][buildman.name] += sum(i.size for i in packages)


def dashboard(request: HttpRequest) -> HttpResponse:
    """Dashboard view"""
    now = timezone.localtime()
    current_timezone = timezone.get_current_timezone()
    bot_days = [now.date() - dt.timedelta(days=days) for days in range(6, -1, -1)]
    builds_over_time: dict[dt.date, defaultdict[str, int]] = {
        day: defaultdict(int) for day in bot_days
    }
    machines = [MachineInfo(i) for i in BuildDB.list_machines()]
    machines.sort(key=lambda m: m.build_count, reverse=True)
    color_start = Color(*GBP_SETTINGS.get("COLOR_START", (80, 69, 117)))
    color_end = Color(*GBP_SETTINGS.get("COLOR_END", (221, 218, 236)))
    context: DashboardContext = {
        "bot_days": [datetime.strftime("%A") for datetime in bot_days],
        "build_count": BuildDB.count(),
        "builds_to_do": [],
        "build_packages": {},
        "builds_over_time": [],
        "built_recently": [],
        "latest_builds": [],
        "machine_colors": [
            str(color) for color in gradient(color_start, color_end, len(machines))
        ],
        "machine_dist": [machine.build_count for machine in machines],
        "machines": [machine.name for machine in machines],
        "now": now,
        "package_count": 0,
        "recent_packages": defaultdict(set),
        "total_package_size": defaultdict(int),
        "unpublished_builds_count": 0,
    }

    for builddb in BuildDB.builds():
        buildman = BuildMan(builddb)
        package_metadata(buildman, context)

        day_submitted = builddb.submitted.astimezone(current_timezone).date()
        if day_submitted >= bot_days[0]:
            builds_over_time[day_submitted][buildman.name] += 1

    (
        context["latest_builds"],
        context["built_recently"],
        context["build_packages"],
    ) = get_build_summary(now, machines)
    context["unpublished_builds_count"] = len(
        [build for build in context["latest_builds"] if not build.published()]
    )
    context["builds_over_time"] = bot_to_list(builds_over_time, machines, bot_days)
    context["builds_to_do"] = [BuildMan(i) for i in BuildDB.builds(completed=None)]

    # https://stackoverflow.com/questions/4764110/django-template-cant-loop-defaultdict
    context["recent_packages"].default_factory = None

    return render(request, "gentoo_build_publisher/dashboard.html", context)
