"""Managers"""
from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from difflib import Differ
from functools import cached_property
from typing import Iterator, Optional

from gentoo_build_publisher import io
from gentoo_build_publisher.build import (
    BuildID,
    Change,
    GBPMetadata,
    Package,
    PackageMetadata,
    Status,
)
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

    def record(self, build_id: BuildID) -> BuildRecord:
        """Return BuildRecord for this build.

        If we already have one, return it.
        Otherwise if a record exists in the RecordDB, get it from the RecordDB.
        Otherwize create an "empty" record.
        """
        try:
            return self.records.get(build_id)
        except RecordNotFound:
            return BuildRecord(build_id)

    def publish(self, build_id: BuildID) -> None:
        """Publish the build"""
        if not self.pulled(build_id):
            self.pull(build_id)

        self.storage.publish(build_id)

    def published(self, build_id: BuildID) -> bool:
        """Return True if this Build is published"""
        return self.storage.published(build_id)

    def pull(self, build_id) -> None:
        """pull the Build to storage"""
        if self.pulled(build_id):
            return

        record = self.record(build_id)
        self.records.save(
            record, submitted=record.submitted or utcnow().replace(tzinfo=timezone.utc)
        )
        previous = self.records.previous_build(build_id)

        if previous:
            previous_build = previous.id
        else:
            previous_build = None

        logger.info("Pulling build: %s", build_id)

        chunk_size = self.jenkins.config.download_chunk_size
        tmpdir = str(self.storage.tmpdir)
        with tempfile.TemporaryFile(buffering=chunk_size, dir=tmpdir) as temp:
            logger.info("Downloading build: %s", build_id)
            io.write_chunks(temp, self.jenkins.download_artifact(build_id))

            logger.info("Downloaded build: %s", build_id)
            temp.seek(0)

            byte_stream = io.read_chunks(temp, chunk_size)
            self.storage.extract_artifact(build_id, byte_stream, previous_build)

        logging.info("Pulled build %s", build_id)

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
        self.storage.set_metadata(build_id, gbp_metadata(jenkins_metadata, packages))

    def pulled(self, build_id: BuildID) -> bool:
        """Return true if the Build has been pulled"""
        return self.storage.pulled(build_id)

    def delete(self, build_id: BuildID) -> None:
        """Delete this build"""
        self.records.delete(build_id)
        self.storage.delete(build_id)

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

    def get_packages(self, build_id: BuildID) -> list[Package]:
        """Return the list of packages for this build"""
        return self.storage.get_packages(build_id)

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

    def search_notes(self, machine: str, key: str) -> Iterator[BuildID]:
        """search notes for given machine"""
        return (record.id for record in self.records.search_notes(machine, key))

    def diff_binpkgs(self, left: BuildID, right: BuildID) -> Iterator[Change]:
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


class MachineInfo:  # pylint: disable=too-few-public-methods
    """Data type for machine metadata

    Has the following attributes:

        name: str
        build_count: int
        latest_build: Optional[BuildID]
        published_build: Optional[BuildID]
    """

    # pylint: disable=missing-docstring

    def __init__(self, name):
        self.name = name
        self.build_publisher = BuildPublisher()

    @cached_property
    def build_count(self) -> int:
        return self.build_publisher.records.count(self.name)

    @cached_property
    def builds(self) -> list[BuildID]:
        return [
            record.id for record in self.build_publisher.records.query(name=self.name)
        ]

    @cached_property
    def latest_build(self) -> BuildID | None:
        record = self.build_publisher.records.latest_build(self.name)

        return None if record is None else record.id

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
