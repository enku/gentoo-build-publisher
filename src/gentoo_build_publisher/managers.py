"""Managers"""
from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from difflib import Differ
from typing import Iterator, Optional

from yarl import URL

from gentoo_build_publisher import io
from gentoo_build_publisher.build import (
    BuildID,
    Change,
    GBPMetadata,
    Package,
    PackageMetadata,
    Status,
)
from gentoo_build_publisher.db import BuildDB, BuildRecord
from gentoo_build_publisher.jenkins import Jenkins, JenkinsMetadata
from gentoo_build_publisher.purge import Purger
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import Storage

logger = logging.getLogger(__name__)
utcnow = datetime.utcnow


class Build:
    """Pulls a build's db, jenkins and storage all together"""

    def __init__(
        self,
        build: BuildID | BuildRecord,
        *,
        jenkins: Optional[Jenkins] = None,
        storage: Optional[Storage] = None,
    ):
        self.db = BuildDB  # pylint: disable=invalid-name

        if isinstance(build, BuildID):
            self.id = build  # pylint: disable=invalid-name
            self._record = None  # fetch lazily
        elif isinstance(build, BuildRecord):
            self.id = build.id
            self._record = build
        else:
            raise TypeError(
                "build argument must be one of [BuildID, BuildRecord]."
                f" Got {type(build).__name__}."
            )

        if jenkins is None:
            self.jenkins = Jenkins.from_settings(Settings.from_environ())
        else:
            self.jenkins = jenkins

        if storage is None:
            self.storage = Storage.from_settings(Settings.from_environ())
        else:
            self.storage = storage

    @property
    def record(self) -> BuildRecord:
        """Return BuildRecord for this build.

        If we already have one, return it.
        Otherwise if a record exists in the BuildDB, get it from the BuildDB.
        Otherwize create an "empty" record.
        """
        if record := self._record:
            return record

        try:
            self._record = self.db.get(self.id)
        except BuildDB.NotFound:
            self._record = BuildRecord(self.id)

        return self._record

    def publish(self):
        """Publish the build"""
        if not self.pulled():
            self.pull()

        self.storage.publish(self.id)

    def published(self) -> bool:
        """Return True if this Build is published"""
        return self.storage.published(self.id)

    def pull(self):
        """pull the Build to storage"""
        if self.pulled():
            return

        self.record.submitted = utcnow().replace(tzinfo=timezone.utc)
        self.db.save(self.record)
        previous = self.db.previous_build(self.id)

        if previous:
            previous_build = previous.id
        else:
            previous_build = None

        logger.info("Pulling build: %s", self.id)

        chunk_size = self.jenkins.config.download_chunk_size
        tmpdir = str(self.storage.tmpdir)
        with tempfile.TemporaryFile(buffering=chunk_size, dir=tmpdir) as temp:
            logger.info("Downloading build: %s", self.id)
            io.write_chunks(temp, self.jenkins.download_artifact(self.id))

            logger.info("Downloaded build: %s", self.id)
            temp.seek(0)

            byte_stream = io.read_chunks(temp, chunk_size)
            self.storage.extract_artifact(self.id, byte_stream, previous_build)

        logging.info("Pulled build %s", self.id)

        self.update_build_metadata()

    def update_build_metadata(self):
        """Update the build's db attributes (based on storage, etc.)"""
        self.record.logs = self.jenkins.get_logs(self.id)
        self.record.completed = utcnow().replace(tzinfo=timezone.utc)
        self.db.save(self.record)

        try:
            packages = self.storage.get_packages(self.id)
        except LookupError:
            return

        jenkins_metadata = self.jenkins.get_metadata(self.id)
        self.storage.set_metadata(self.id, gbp_metadata(jenkins_metadata, packages))

    def save_record(self) -> None:
        """Save the BuildRecord to the database"""
        self.db.save(self.record)

    def pulled(self) -> bool:
        """Return true if the Build has been pulled"""
        return self.storage.pulled(self.id)

    def delete(self):
        """Delete this build"""
        self.db.delete(self.id)
        self.storage.delete(self.id)

    def logs_url(self) -> URL:
        """Return the Jenkins logs url for this Build"""
        return self.jenkins.logs_url(self.id)

    def get_packages(self) -> list[Package]:
        """Return the list of packages for this build"""
        return self.storage.get_packages(self.id)

    @staticmethod
    def schedule_build(name: str) -> str:
        """Schedule a build on jenkins for the given machine name"""
        settings = Settings.from_environ()
        jenkins = Jenkins.from_settings(settings)

        return jenkins.schedule_build(name)

    @classmethod
    def purge(cls, machine: str):
        """Purge old builds for machine"""
        logging.info("Purging builds for %s", machine)
        records = BuildDB.get_records(name=machine)
        purger = Purger(records, key=lambda b: b.submitted.replace(tzinfo=None))

        for record in purger.purge():  # type: BuildRecord
            if not record.keep:
                build = cls(record)
                if not build.published():
                    build.delete()

    @classmethod
    def search_notes(cls, machine: str, key: str) -> Iterator[Build]:
        """search notes for given machine"""
        return (cls(record) for record in BuildDB.search_notes(machine, key))

    @staticmethod
    def diff_binpkgs(left: Build, right: Build) -> Iterator[Change]:
        """Compare two package's binpkgs and generate the differences"""
        if left == right:
            return

        left_packages = [f"{package.cpvb()}\n" for package in left.get_packages()]
        right_packages = [f"{package.cpvb()}\n" for package in right.get_packages()]
        code_map = {"-": "REMOVED", "+": "ADDED"}

        differ = Differ()
        diff = differ.compare(left_packages, right_packages)

        for item in diff:
            if (code := item[0]) not in code_map:
                continue
            cpvb = item[2:].rstrip()

            yield Change(cpvb, Status[code_map[code]])

    def __str__(self) -> str:
        return str(self.id)

    def __eq__(self, other) -> bool:
        return self.id == other.id


class MachineInfo:  # pylint: disable=too-few-public-methods
    """Data type for machine metadata

    Has the following attributes:

        name: str
        build_count: int
        latest_build: Optional[Build]
        published: Optional[Build]
    """

    def __init__(self, machine_name: str):
        latest_build = BuildDB.latest_build(machine_name)
        published = None

        if latest_build is not None:
            current_build = latest_build.id.number

            while current_build:
                build = Build(BuildID(f"{machine_name}.{current_build}"))
                if build.published():
                    published = build
                    break

                current_build -= 1

        self.name: str = machine_name
        self.build_count: int = BuildDB.count(machine_name)
        self.latest_build: Optional[Build] = (
            Build(latest_build.id) if latest_build else None
        )
        self.published: Optional[Build] = published

    def builds(self) -> list[Build]:
        """Return the builds for the given machine"""
        records = BuildDB.get_records(name=self.name)

        return [Build(record) for record in records]


def diff_notes(left: Build, right: Build, header: str = "") -> str:
    """Return package diff as a string of notes

    If there are no changes, return an empty string
    """
    changeset = [
        item for item in Build.diff_binpkgs(left, right) if item.status.is_a_build()
    ]
    changeset.sort(key=lambda i: i.item)

    note = "\n".join(f"* {i.item}" for i in changeset)

    if note and header:
        note = f"{header}\n{note}"

    return note


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
