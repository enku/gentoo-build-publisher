# pylint: disable=missing-docstring
import datetime as dt

from gentoo_build_publisher import publisher
from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.types import Build, Package
from gentoo_build_publisher.utils.time import SECONDS_PER_DAY, lapsed, localtime

type MachineName = str


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
