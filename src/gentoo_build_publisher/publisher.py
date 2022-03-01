"""Managers"""
from __future__ import annotations

import logging
import math
import tempfile
from datetime import datetime, timezone
from difflib import Differ
from functools import cached_property
from typing import Any, Iterator

from . import io
from .jenkins import Jenkins, JenkinsMetadata
from .purge import Purger
from .records import BuildRecord, RecordDB, RecordNotFound, Records
from .settings import Settings
from .storage import Storage
from .types import Build, Change, GBPMetadata, Package, PackageMetadata, Status

logger = logging.getLogger(__name__)
utcnow = datetime.utcnow


class BuildPublisher:
    """Pulls a build's db, jenkins and storage all together"""

    jenkins: Jenkins
    storage: Storage
    db: RecordDB

    def __init__(self, *, jenkins: Jenkins, storage: Storage, records: RecordDB):
        self.jenkins = jenkins
        self.storage = storage
        self.records = records

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
        Otherwize create an "empty" record.
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

    def published(self, build: Build) -> bool:
        """Return True if this Build is published"""
        return self.storage.published(build)

    def pull(self, build) -> None:
        """pull the Build to storage"""
        if self.pulled(build):
            return

        record = self.record(build)
        self.records.save(
            record, submitted=record.submitted or utcnow().replace(tzinfo=timezone.utc)
        )
        previous = self.records.previous_build(record)

        logger.info("Pulling build: %s", build)

        chunk_size = self.jenkins.config.download_chunk_size
        tmpdir = str(self.storage.tmpdir)
        with tempfile.TemporaryFile(buffering=chunk_size, dir=tmpdir) as temp:
            logger.info("Downloading build: %s", build)
            io.write_chunks(temp, self.jenkins.download_artifact(build))

            logger.info("Downloaded build: %s", build)
            temp.seek(0)

            byte_stream = io.read_chunks(temp, chunk_size)
            self.storage.extract_artifact(build, byte_stream, previous)

        logging.info("Pulled build %s", build)

        self._update_build_metadata(record)

    def _update_build_metadata(self, record: BuildRecord) -> None:
        """Update the build's db attributes (based on storage, etc.)"""
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
            return

        self.storage.set_metadata(record, self.gbp_metadata(jenkins_metadata, packages))

    def pulled(self, build: Build) -> bool:
        """Return true if the Build has been pulled"""
        return self.storage.pulled(build)

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

    @staticmethod
    def _purge_key(record: BuildRecord) -> datetime:
        """Purge key for build records.  Purge on submitted date"""
        submitted = record.submitted or datetime.fromtimestamp(0)

        return submitted.replace(tzinfo=None)

    def purge(self, machine: str) -> None:
        """Purge old builds for machine"""

        record: BuildRecord
        logging.info("Purging builds for %s", machine)
        records = self.records.query(machine=machine)
        purger = Purger(records, key=self._purge_key)

        for record in purger.purge():
            if not (record.keep or self.published(record)):
                self.delete(record)

    def search_notes(self, machine: str, key: str) -> Iterator[BuildRecord]:
        """search notes for given machine"""
        return (record for record in self.records.search_notes(machine, key))

    def diff_binpkgs(self, left: Build, right: Build) -> Iterator[Change]:
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
        return self.records.latest_build(machine, completed)

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

    def __init__(self, machine):
        self.machine = machine

    @cached_property
    def build_count(self) -> int:
        return len(self.builds)

    @cached_property
    def builds(self) -> list[BuildRecord]:
        return [*build_publisher.records.query(machine=self.machine)]

    @cached_property
    def latest_build(self) -> BuildRecord | None:
        try:
            return next(build for build in self.builds if build.completed)
        except StopIteration:
            return None

    @cached_property
    def published_build(self) -> Build | None:
        try:
            return next(
                Build(build.id)
                for build in self.builds
                if build_publisher.published(build)
            )
        except StopIteration:
            return None


# The whole purpose of this is so that we can have a "singleton" instance of
# BuildPublisher. But we can't intantiate it here at import time because for the tests
# we're overriding the environment variables on each test and the instance depends on
# environment variables plus those variables don't exist yet when the test runner starts
# importing. So what we do here is create a "lazy" subclass that doesn't actually
# instantiate the instance until __getattr__ is called and have the TestCase's .setUp()
# remove (reset) the instance on each test.
class SystemPublisher(BuildPublisher):
    """Build publisher singleton"""

    def __init__(self):  # pylint: disable=super-init-not-called
        self._publisher = None

    def __getattr__(self, name: str) -> Any:
        if self._publisher is None:
            self._publisher = BuildPublisher.from_settings(Settings.from_environ())

        return getattr(self._publisher, name)

    def reset(self, replacement: BuildPublisher | None = None) -> None:
        """Reset the instance"""
        self._publisher = replacement


build_publisher = SystemPublisher()
