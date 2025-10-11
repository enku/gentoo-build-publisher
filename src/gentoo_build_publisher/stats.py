# pylint: disable=missing-docstring
import datetime as dt
from dataclasses import dataclass
from typing import Any, Self, cast

from gentoo_build_publisher import publisher
from gentoo_build_publisher.cache import GBPSiteCache
from gentoo_build_publisher.cache import cache as site_cache
from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.types import Build, Package
from gentoo_build_publisher.utils.time import SECONDS_PER_DAY, lapsed, localtime

type MachineName = str


@dataclass(kw_only=True, frozen=True)
class Stats:
    # pylint: disable=too-many-instance-attributes

    machines: list[MachineName]
    machine_info: dict[MachineName, MachineInfo]
    package_counts: dict[MachineName, int]
    build_packages: dict[BuildRecord, list[str]]
    latest_build: dict[MachineName, BuildRecord | None]
    latest_published: dict[MachineName, BuildRecord | None]
    recent_packages: dict[MachineName, list[Package]]
    total_package_size: dict[MachineName, int]
    builds_by_day: dict[MachineName, dict[dt.date, int]]
    packages_by_day: dict[MachineName, dict[dt.date, list[Package]]]

    @classmethod
    def collect(cls) -> Self:
        sc = StatsCollector()
        machines = sc.machines
        machine_info = {machine: sc.machine_info(machine) for machine in machines}
        package_counts = {machine: sc.package_count(machine) for machine in machines}
        total_package_size = {
            machine: sc.total_package_size(machine) for machine in machines
        }
        recent_packages = {machine: sc.recent_packages(machine) for machine in machines}

        build_packages = {
            latest: sc.build_packages(latest)
            for machine in machines
            if (latest := sc.latest_build(machine))
        }
        packages_by_day = {machine: sc.packages_by_day(machine) for machine in machines}
        latest_published = {
            machine: sc.latest_published(machine) for machine in machines
        }
        latest_build = {machine: sc.latest_build(machine) for machine in machines}
        builds_by_day = {machine: sc.builds_by_day(machine) for machine in machines}

        return cls(
            machines=machines,
            machine_info=machine_info,
            package_counts=package_counts,
            build_packages=build_packages,
            total_package_size=total_package_size,
            recent_packages=recent_packages,
            packages_by_day=packages_by_day,
            latest_published=latest_published,
            latest_build=latest_build,
            builds_by_day=builds_by_day,
        )

    @classmethod
    def with_cache(cls, cache: GBPSiteCache = site_cache, **kwargs: Any) -> Self:
        """Get or create Stats from the given cache

        If the item is in the given cache with the given key, return it.
        Otherwise collect the stats and cache it. Then return it.
        """
        if (stats := getattr(cache, "stats", None)) is None:
            stats = cache.stats = cls.collect()

        return cast(Self, stats)


class StatsCollector:
    """Interface to collect statistics about the Publisher"""

    def machine_info(self, machine: MachineName) -> MachineInfo:
        """Return the MachineInfo object for the given machine"""
        return MachineInfo(machine)

    @property
    def machines(self) -> list[MachineName]:
        """Returns a list of machines with builds

        Machines are ordered by build count (descending), then machine name (ascending)
        """
        return sorted(
            (m.machine for m in publisher.machines()),
            key=lambda m: (-1 * self.machine_info(m).build_count, m),
        )

    def package_count(self, machine: MachineName) -> int:
        """Return the total number of completed builds for the given machine"""
        total = 0

        for build in self.machine_info(machine).builds:
            metadata = publisher.build_metadata(build)
            if metadata and build.completed:
                total += metadata.packages.total

        return total

    def build_packages(self, build: Build) -> list[str]:
        """Return a list of CPVs build in the given build"""
        metadata = publisher.build_metadata(build)
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
            if not (metadata := publisher.build_metadata(build)):
                continue
            packages.update(metadata.packages.built)
            if len(packages) >= maximum:
                break

        return sorted(packages, key=lambda p: p.build_time, reverse=True)[:maximum]

    def total_package_size(self, machine: MachineName) -> int:
        """Return the total size (bytes) of all packages in all builds for machine"""
        total = 0

        for record in self.machine_info(machine).builds:
            if record.completed and (metadata := publisher.build_metadata(record)):
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
            metadata = publisher.build_metadata(build)

            pbd.setdefault(date, set()).update(metadata.packages.built)

        return {date: list(packages) for date, packages in pbd.items()}
