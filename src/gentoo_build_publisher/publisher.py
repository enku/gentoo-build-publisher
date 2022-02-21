"""Managers"""
from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from difflib import Differ
from functools import cached_property
from typing import Iterator, Optional

from . import io
from .jenkins import Jenkins, JenkinsMetadata
from .purge import Purger
from .records import RecordDB, RecordNotFound, Records
from .settings import Settings
from .storage import Storage
from .types import (
    Build,
    BuildID,
    BuildRecord,
    Change,
    GBPMetadata,
    Package,
    PackageMetadata,
    Status,
)

logger = logging.getLogger(__name__)
utcnow = datetime.utcnow


class BuildPublisher:
    """Pulls a build's db, jenkins and storage all together"""

    jenkins: Jenkins
    storage: Storage
    db: RecordDB

    def __init__(
        self,
        *,
        jenkins: Optional[Jenkins] = None,
        storage: Optional[Storage] = None,
        records: Optional[RecordDB] = None,
    ):
        if jenkins is None:
            self.jenkins = self.environ_jenkins
        else:
            self.jenkins = jenkins

        if storage is None:
            self.storage = self.environ_storage
        else:
            self.storage = storage

        if records is None:
            self.records = Records.from_settings(Settings.from_environ())
        else:
            self.records = records

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
            return BuildRecord(build)

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
        previous = self.records.previous_build(build)

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
        build_id = record.id
        self.records.save(
            record,
            logs=self.jenkins.get_logs(build_id),
            completed=utcnow().replace(tzinfo=timezone.utc),
        )

        try:
            packages = self.storage.get_packages(build_id)
        except LookupError:
            return

        jenkins_metadata = self.jenkins.get_metadata(build_id)
        self.storage.set_metadata(
            build_id, self.gbp_metadata(jenkins_metadata, packages)
        )

    def pulled(self, build: Build) -> bool:
        """Return true if the Build has been pulled"""
        return self.storage.pulled(build)

    def delete(self, build: Build) -> None:
        """Delete this build"""
        self.records.delete(build)
        self.storage.delete(build)

    @property
    def environ_jenkins(self) -> Jenkins:
        """Get or create Jenkins configured from environment variables"""
        cls = type(self)

        if not hasattr(cls, "jenkins"):
            cls.jenkins = Jenkins.from_settings(Settings.from_environ())

        return cls.jenkins

    @property
    def environ_storage(self) -> Storage:
        """Get or create Storage configured from environment variables"""
        cls = type(self)

        if not hasattr(cls, "storage"):
            cls.storage = Storage.from_settings(Settings.from_environ())

        return cls.storage

    def get_packages(self, build: Build) -> list[Package]:
        """Return the list of packages for this build"""
        return self.storage.get_packages(build)

    def schedule_build(self, name: str) -> str:
        """Schedule a build on jenkins for the given machine name"""
        return self.jenkins.schedule_build(name)

    def purge(self, machine: str) -> None:
        """Purge old builds for machine"""
        record: BuildRecord
        logging.info("Purging builds for %s", machine)
        records = self.records.query(name=machine)
        purger = Purger(records, key=lambda b: b.submitted.replace(tzinfo=None))

        for record in purger.purge():
            if not record.keep:
                build_id = record.id
                if not self.published(build_id):
                    self.delete(build_id)

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
        return [MachineInfo(i, self) for i in self.records.list_machines()]

    def latest_build(self, name: str, completed: bool = False) -> BuildRecord | None:
        """Return the latest completed build for the given machine name"""
        return self.records.latest_build(name, completed)

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
                    if package.build_time >= jenkins_metadata.timestamp / 1000
                ],
            ),
        )


class MachineInfo:
    """Data type for machine metadata

    Has the following attributes:

        name: str
        build_count: int
        latest_build: Optional[BuildRecord]
        published_build: Optional[BuildID]
    """

    # pylint: disable=missing-docstring

    def __init__(self, name, build_publisher: BuildPublisher):
        self.name = name
        self.build_publisher = build_publisher

    @cached_property
    def build_count(self) -> int:
        return self.build_publisher.records.count(self.name)

    @cached_property
    def builds(self) -> list[BuildRecord]:
        return [*self.build_publisher.records.query(name=self.name)]

    @cached_property
    def latest_build(self) -> BuildRecord | None:
        return self.build_publisher.latest_build(self.name)

    @cached_property
    def published_build(self) -> BuildID | None:
        if not (latest := self.latest_build):
            return None

        number = latest.number

        while number:
            build_id = BuildID(f"{self.name}.{number}")
            if self.build_publisher.published(build_id):
                return build_id

            number -= 1

        return None
