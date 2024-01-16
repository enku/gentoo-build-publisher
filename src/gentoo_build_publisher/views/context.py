"""GBP View Context Utilities"""
import datetime as dt
from dataclasses import dataclass, field
from typing import TypedDict

from django.utils import timezone

from gentoo_build_publisher.common import Build, CacheProtocol, Package
from gentoo_build_publisher.publisher import BuildPublisher
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.utils.time import SECONDS_PER_DAY, lapsed
from gentoo_build_publisher.views.utils import (
    Gradient,
    StatsCollector,
    days_strings,
    get_chart_days,
    gradient_colors,
)

MAX_DISPLAYED_PKGS = 12


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


def create_dashboard_context(input_context: ViewInputContext) -> DashboardContext:
    """Initialize and return DashboardContext"""
    publisher = input_context.publisher
    sc = StatsCollector(publisher, input_context.cache)
    chart_days = get_chart_days(input_context.now, input_context.days)

    recent_packages: dict[str, set[str]] = {}
    for machine in sc.machines:
        if record := sc.latest_build(machine):
            for package in sc.build_packages(record):
                if len(recent_packages) < MAX_DISPLAYED_PKGS:
                    recent_packages.setdefault(package, set()).add(machine)

    return {
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
    latest_build = sc.latest_build(machine)

    if not latest_build:
        raise ValueError(f"machine {machine} has no builds")

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
