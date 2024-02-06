"""Functions/data to support the dashboard view"""

from __future__ import annotations

import datetime as dt
from functools import lru_cache
from typing import Any, TypeAlias

from django.http import HttpRequest

from gentoo_build_publisher import publisher
from gentoo_build_publisher.common import Build, CacheProtocol, GBPMetadata, Package
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.utils import Color
from gentoo_build_publisher.utils.time import SECONDS_PER_DAY, lapsed, localtime

BuildID: TypeAlias = str  # pylint: disable=invalid-name
CPV: TypeAlias = str  # pylint: disable=invalid-name
Gradient: TypeAlias = list[str]
MachineName: TypeAlias = str


_NOT_FOUND = object()


class StatsCollector:
    """Interface to collect statistics about the Publisher"""

    def __init__(self, cache: CacheProtocol) -> None:
        self.cache = cache

    @lru_cache
    def machine_info(self, machine: MachineName) -> publisher.MachineInfo:
        """Return the MachineInfo object for the given machine"""
        return publisher.MachineInfo(machine)

    @property
    @lru_cache
    def machines(self) -> list[MachineName]:
        """Returns a list of machines with builds

        Machines are ordered by build count (descending), then machine name (ascending)
        """
        return sorted(
            (m.machine for m in publisher.machines()),
            key=lambda m: (-1 * self.machine_info(m).build_count, m),
        )

    @lru_cache
    def package_count(self, machine: MachineName) -> int:
        """Return the total number of completed builds for the given machine"""
        total = 0

        for build in self.machine_info(machine).builds:
            metadata = get_metadata(build, self.cache)
            if metadata and build.completed:
                total += metadata.packages.total

        return total

    def build_packages(self, build: Build) -> list[str]:
        """Return a list of CPVs build in the given build"""
        metadata = get_metadata(build, self.cache)
        return [i.cpv for i in metadata.packages.built] if metadata is not None else []

    def latest_build(self, machine: MachineName) -> BuildRecord | None:
        """Return the latest build for the given machine

        If the Machine has no builds, return None.
        """
        return self.machine_info(machine).latest_build

    def latest_published(self, machine: MachineName) -> BuildRecord | None:
        """Return the latest build for the given machine if that build is published

        Otherwise return None.
        """
        if latest := self.latest_build(machine):
            if published := self.machine_info(machine).published_build:
                if latest == publisher.record(published):
                    return latest
        return None

    def recent_packages(self, machine: MachineName, maximum: int = 10) -> list[Package]:
        """Return the list of recent packages for a machine (up to maximum)"""
        packages: set[Package] = set()

        for build in self.machine_info(machine).builds:
            if not (metadata := get_metadata(build, self.cache)):
                continue
            packages.update(metadata.packages.built)
            if len(packages) >= maximum:
                break

        return sorted(packages, key=lambda p: p.build_time, reverse=True)[:maximum]

    def total_package_size(self, machine: MachineName) -> int:
        """Return the total size (bytes) of all packages in all builds for machine"""
        total = 0

        for record in self.machine_info(machine).builds:
            if record.completed and (metadata := get_metadata(record, self.cache)):
                total += metadata.packages.size

        return total

    def built_recently(self, build: BuildRecord, now: dt.datetime) -> bool:
        """Return True if the given build was built within 24 hours of the given time"""
        return False if not build.built else lapsed(build.built, now) < SECONDS_PER_DAY

    def builds_by_day(self, machine: MachineName) -> dict[dt.date, int]:
        """Return a dict of count of builds by day for the given machine"""
        bbd: dict[dt.date, int] = {}

        for build in self.machine_info(machine).builds:
            assert build.submitted
            date = localtime(build.submitted).date()
            bbd[date] = bbd.setdefault(date, 0) + 1

        return bbd

    def packages_by_day(self, machine: MachineName) -> dict[dt.date, list[Package]]:
        """Return dict of machine's packages distributed by build date"""
        pbd: dict[dt.date, set[Package]] = {}

        for build in filter(
            lambda b: b.built and b.submitted, self.machine_info(machine).builds
        ):
            date = localtime(build.built).date()

            try:
                metadata = publisher.storage.get_metadata(build)
            except LookupError:
                continue

            pbd.setdefault(date, set()).update(metadata.packages.built)

        return {date: list(packages) for date, packages in pbd.items()}


def days_strings(start: dt.datetime, days: int) -> list[str]:
    """Return list of datetimes from start as strings"""
    fmt = "%A" if days <= 7 else "%x"
    return [datetime.strftime(fmt) for datetime in get_chart_days(start, days)]


def get_metadata(build: Build, cache: CacheProtocol) -> GBPMetadata | None:
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
    request: HttpRequest, key: str, type_: type, fallback: Any
) -> Any:
    """Return given query value from the query params"""
    if (query_value := request.GET.get(key, _NOT_FOUND)) == _NOT_FOUND:
        return fallback
    try:
        return type_(query_value)
    except ValueError:
        return fallback
