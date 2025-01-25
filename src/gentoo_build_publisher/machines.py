"""machines provides utilities for a particular machine.

As opposed to a particular build
"""

from functools import cached_property

from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.types import Build


class MachineInfo:
    """Data type for machine metadata

    Has the following attributes:

        machine: str
        build_count: int
        latest_build: BuildRecord | None
        published_build: Build | None
    """

    def __init__(self, machine: str) -> None:
        # Avoid circular import
        # pylint: disable=cyclic-import,import-outside-toplevel
        from gentoo_build_publisher import publisher

        self.machine = machine
        self.publisher = publisher

    @cached_property
    def build_count(self) -> int:
        """Number of builds held for the machine"""
        return len(self.builds)

    @cached_property
    def builds(self) -> list[BuildRecord]:
        """List of builds held for the machine"""
        return list(self.publisher.repo.build_records.for_machine(self.machine))

    @cached_property
    def latest_build(self) -> BuildRecord | None:
        """The latest completed build, or None"""
        return next((build for build in self.builds if build.completed), None)

    @cached_property
    def published_build(self) -> Build | None:
        """The latest published build, or None"""
        publisher = self.publisher
        builds = (Build.from_id(b.id) for b in self.builds if publisher.published(b))
        return next(builds, None)

    @cached_property
    def tags(self) -> list[str]:
        """All the machines build tags"""
        publisher = self.publisher
        return sorted(tag for build in self.builds for tag in publisher.tags(build))
