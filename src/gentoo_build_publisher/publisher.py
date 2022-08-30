"""The Publisher

When we think about a "build" In Gentoo Build Publisher there are three subsystems that,
when combined, represent the the build:

    * Jenkins: the connection to the Jenkins instance as well as the artifacts it hosts
    * Storage: the file system storage responsible where artifacts are pulled and
      extracted and eventually hosted by GBP.
    * RecordDB: The (relational) database that holds various metadata not held in
      Storage

The above all classes (or Protocols) that operate independently.  There exists a
facade for these subsystems. This is the BuildPublisher.  For example, when a build is
pulled, then BuildPublisher.pull(build) ensures the artifact gets pull from Jenkins, get's
extracted into Storage, and appropriate metadata is created in the RecordDB.  Likewise
when a build is deleted (BuildPublisher.delete(build)) then it makes sure that the
Storage and Record are removed.
"""
from __future__ import annotations

import logging
import math
import tempfile
from collections.abc import Iterable
from datetime import datetime, timezone
from difflib import Differ
from functools import cached_property

from pydispatch import Dispatcher

from gentoo_build_publisher import io
from gentoo_build_publisher.jenkins import Jenkins, JenkinsMetadata
from gentoo_build_publisher.purge import Purger
from gentoo_build_publisher.records import (
    BuildRecord,
    RecordDB,
    RecordNotFound,
    Records,
)
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import Storage
from gentoo_build_publisher.types import (
    Build,
    Change,
    GBPMetadata,
    Package,
    PackageMetadata,
    Status,
)

logger = logging.getLogger(__name__)
utcnow = datetime.utcnow


class PublisherDispatcher(Dispatcher):
    """BuildPublisher event dispatcher"""

    _events_ = ["published", "pulled"]


class BuildPublisher:
    """Pulls a build's db, jenkins and storage all together"""

    def __init__(self, *, jenkins: Jenkins, storage: Storage, records: RecordDB):
        self.jenkins = jenkins
        self.storage = storage
        self.records = records
        self.dispatcher = PublisherDispatcher()

    @classmethod
    def from_settings(cls, settings: Settings) -> BuildPublisher:
        """Instatiate from settings"""
        jenkins = Jenkins.from_settings(settings)
        storage = Storage.from_settings(settings)
        records = Records.from_settings(settings)

        return cls(jenkins=jenkins, storage=storage, records=records)

    def record(self, build: Build) -> BuildRecord:
        """Return BuildRecord for this build.

        If we already have one, return it.
        Otherwise if a record exists in the RecordDB, get it from the RecordDB.
        Otherwise create an "empty" record.
        """
        if isinstance(build, BuildRecord):
            return build

        try:
            return self.records.get(build)
        except RecordNotFound:
            return BuildRecord(str(build))

    def publish(self, build: Build) -> None:
        """Publish the build"""
        if not self.pulled(build):
            self.pull(build)

        self.storage.publish(build)
        self.dispatcher.emit("published", build=self.record(build))

    def tag(self, build: Build, tag_name: str) -> None:
        """Tag a build with the given name

        Unlike publish(), does not auto-pull the build
        """
        self.storage.tag(build, tag_name)

    def untag(self, machine: str, tag_name: str) -> None:
        """Remove the given tag name from the machine

        Can also be used to unpublish builds if tag_name is the empty string.
        """
        self.storage.untag(machine, tag_name)

    def tags(self, build: Build) -> list[str]:
        """Return the list of tags for the given build

        Does not include the empty (published) tag.
        """
        return [tag for tag in self.storage.get_tags(build) if tag]

    def published(self, build: Build) -> bool:
        """Return True if this Build is published"""
        return self.storage.published(build)

    def pull(self, build: Build) -> bool:
        """pull the Build to storage"""
        if self.pulled(build):
            return False

        record = self.record(build)
        self.records.save(
            record, submitted=record.submitted or utcnow().replace(tzinfo=timezone.utc)
        )
        previous = self.records.previous(record)

        logger.info("Pulling build: %s", build)

        chunk_size = self.jenkins.config.download_chunk_size
        tmpdir = str(self.storage.tmpdir)
        with tempfile.TemporaryFile(buffering=chunk_size, dir=tmpdir) as temp:
            logger.info("Downloading build: %s", build)
            temp.writelines(self.jenkins.download_artifact(build))

            logger.info("Downloaded build: %s", build)
            temp.seek(0)

            byte_stream = io.read_chunks(temp, chunk_size)
            self.storage.extract_artifact(build, byte_stream, previous)

        logging.info("Pulled build %s", build)

        self._update_build_metadata(record)

        return True

    def _update_build_metadata(self, record: BuildRecord) -> None:

        packages: list[Package] | None = None
        gbp_metadata: GBPMetadata | None = None
        jenkins_metadata = self.jenkins.get_metadata(record)

        self.records.save(
            record,
            logs=self.jenkins.get_logs(record),
            completed=utcnow().replace(tzinfo=timezone.utc),
            built=datetime.utcfromtimestamp(jenkins_metadata.timestamp / 1000).replace(
                tzinfo=timezone.utc
            ),
        )

        try:
            packages = self.storage.get_packages(record)
        except LookupError:
            pass
        else:
            gbp_metadata = self.gbp_metadata(jenkins_metadata, packages)
            self.storage.set_metadata(record, gbp_metadata)

        self.dispatcher.emit(
            "pulled", build=record, packages=packages, gbp_metadata=gbp_metadata
        )

    def pulled(self, build: Build) -> bool:
        """Return true if the Build has been pulled"""
        return self.storage.pulled(build) and self.record(build).completed is not None

    def delete(self, build: Build) -> None:
        """Delete this build"""
        self.records.delete(build)
        self.storage.delete(build)

    def get_packages(self, build: Build) -> list[Package]:
        """Return the list of packages for this build"""
        return self.storage.get_packages(build)

    def schedule_build(self, machine: str) -> str:
        """Schedule a build on jenkins for the given machine name"""
        return self.jenkins.schedule_build(machine)

    def purge(self, machine: str) -> None:
        """Purge old builds for machine"""
        logging.info("Purging builds for %s", machine)
        records = self.records.for_machine(machine)
        purger = Purger(records, key=BuildRecord.purge_key)

        for record in purger.purge():
            if not (record.keep or self.storage.get_tags(record)):
                self.delete(record)

    def search_notes(self, machine: str, key: str) -> list[BuildRecord]:
        """search notes for given machine"""
        return list(self.records.search_notes(machine, key))

    def diff_binpkgs(self, left: Build, right: Build) -> Iterable[Change]:
        """Compare two package's binpkgs and generate the differences"""
        if left == right:
            return

        left_packages = [f"{package.cpvb()}\n" for package in self.get_packages(left)]
        right_packages = [f"{package.cpvb()}\n" for package in self.get_packages(right)]
        code_map = {"-": "REMOVED", "+": "ADDED"}

        differ = Differ()
        diff = differ.compare(left_packages, right_packages)

        for item in diff:
            if (code := item[0]) not in code_map:
                continue
            cpvb = item[2:].rstrip()

            yield Change(cpvb, Status[code_map[code]])

    def machines(self) -> list[MachineInfo]:
        """Return list of machines with metadata"""
        return [MachineInfo(i) for i in self.records.list_machines()]

    def latest_build(self, machine: str, completed: bool = False) -> BuildRecord | None:
        """Return the latest completed build for the given machine name"""
        return self.records.latest(machine, completed)

    @staticmethod
    def gbp_metadata(
        jenkins_metadata: JenkinsMetadata, packages: list[Package]
    ) -> GBPMetadata:
        """Generate GBPMetadata given JenkinsMetadata and Packages"""
        return GBPMetadata(
            build_duration=jenkins_metadata.duration,
            packages=PackageMetadata(
                total=len(packages),
                size=sum(package.size for package in packages),
                built=[
                    package
                    for package in packages
                    if package.build_time
                    >= math.floor(jenkins_metadata.timestamp / 1000)
                ],
            ),
        )


class MachineInfo:
    """Data type for machine metadata

    Has the following attributes:

        machine: str
        build_count: int
        latest_build: Optional[BuildRecord]
        published_build: Optional[Build]
    """

    # pylint: disable=missing-docstring

    def __init__(self, machine: str):
        self.machine = machine

    @cached_property
    def build_count(self) -> int:
        return len(self.builds)

    @cached_property
    def builds(self) -> list[BuildRecord]:
        publisher = get_publisher()

        return [*publisher.records.for_machine(self.machine)]

    @cached_property
    def latest_build(self) -> BuildRecord | None:
        try:
            return next(build for build in self.builds if build.completed)
        except StopIteration:
            return None

    @cached_property
    def published_build(self) -> Build | None:
        publisher = get_publisher()

        try:
            return next(
                Build(build.id) for build in self.builds if publisher.published(build)
            )
        except StopIteration:
            return None

    @cached_property
    def tags(self) -> list[str]:
        machine_tags = []
        publisher = get_publisher()

        for build in self.builds:
            machine_tags.extend(publisher.tags(build))

        machine_tags.sort()

        return machine_tags


_PUBLISHER: BuildPublisher | None = None


def get_publisher() -> BuildPublisher:
    """Return the "system" publisher"""
    global _PUBLISHER  # pylint: disable=global-statement

    if _PUBLISHER is None:
        _PUBLISHER = BuildPublisher.from_settings(Settings.from_environ())

    return _PUBLISHER
