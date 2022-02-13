"""Managers"""
from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from difflib import Differ
from pathlib import Path
from typing import Iterator, Optional, Union

from yarl import URL

from gentoo_build_publisher import io
from gentoo_build_publisher.build import (
    Build,
    Change,
    Content,
    GBPMetadata,
    Package,
    PackageMetadata,
    Status,
)
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.jenkins import JenkinsBuild, JenkinsMetadata
from gentoo_build_publisher.jenkins import schedule_build as schedule_jenkins_build
from gentoo_build_publisher.purge import Purger
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import Storage

logger = logging.getLogger(__name__)
utcnow = datetime.utcnow


class BuildMan:
    """Pulls a build's db, jenkins and storage all together"""

    def __init__(
        self,
        build: Union[Build, BuildDB],
        *,
        jenkins_build: Optional[JenkinsBuild] = None,
        storage: Optional[Storage] = None,
    ):
        if isinstance(build, Build):
            self.build = build
            self._db: Optional[BuildDB] = None
        elif isinstance(build, BuildDB):
            self.build = Build(name=build.name, number=build.number)
            self._db = build
        else:
            raise TypeError(
                "build argument must be one of [Build, BuildDB]."
                f" Got {type(build).__name__}."
            )

        self.name = self.build.name
        self.number = self.build.number

        if jenkins_build is None:
            self.jenkins_build = JenkinsBuild.from_settings(
                self.build, Settings.from_environ()
            )
        else:
            self.jenkins_build = jenkins_build

        if storage is None:
            self.storage = Storage.from_settings(Settings.from_environ())
        else:
            self.storage = storage

    @property
    def id(self):  # pylint: disable=invalid-name
        """Return the BuildDB id or None if there is no database model"""
        return self.db.id if self.db is not None else None

    @property
    def db(self):  # pylint: disable=invalid-name
        """The database object (or None)"""
        if not self._db:
            try:
                self._db = BuildDB.get(self.build)
            except BuildDB.NotFound:
                pass

        return self._db

    def publish(self):
        """Publish the build"""
        if not self.pulled():
            self.pull()

        self.storage.publish(self.build.id)

    def published(self) -> bool:
        """Return True if this Build is published"""
        return self.storage.published(self.build.id)

    def pull(self):
        """pull the Build to storage"""
        if self.pulled():
            return

        build = self.build
        storage = self.storage
        jenkins = self.jenkins_build

        self._db = self._db or BuildDB.get_or_create(build)
        previous = BuildDB.previous_build(self._db)

        if previous:
            previous_build = previous.build.id
        else:
            previous_build = None

        logger.info("Pulling build: %s", build)

        chunk_size = jenkins.jenkins.download_chunk_size
        tmpdir = str(self.storage.tmpdir)
        with tempfile.TemporaryFile(buffering=chunk_size, dir=tmpdir) as temp:
            logger.info("Downloading build: %s", build)
            io.write_chunks(temp, jenkins.download_artifact())

            logger.info("Downloaded build: %s", build)
            temp.seek(0)

            byte_stream = io.read_chunks(temp, chunk_size)
            storage.extract_artifact(self.build.id, byte_stream, previous_build)

        logging.info("Pulled build %s", build)

        self.update_build_metadata()

    def update_build_metadata(self):
        """Update the build's db attributes (based on storage, etc.)"""
        self._db = self._db or BuildDB.get_or_create(self.build)

        self.db.logs = self.jenkins_build.get_logs()
        self.db.completed = utcnow().replace(tzinfo=timezone.utc)
        self.db.save()

        try:
            packages = self.storage.get_packages(self.build.id)
        except LookupError:
            return

        jenkins_metadata = self.jenkins_build.get_metadata()
        self.storage.set_metadata(
            self.build.id, gbp_metadata(jenkins_metadata, packages)
        )

    def pulled(self) -> bool:
        """Return true if the Build has been pulled"""
        return self.storage.pulled(self.build.id)

    def delete(self):
        """Delete this build"""
        if self.db is not None:
            self.db.delete()

        self.storage.delete(self.build.id)

    def logs_url(self) -> URL:
        """Return the JenkinsBuild logs url for this Build"""
        return self.jenkins_build.logs_url()

    def get_packages(self) -> list[Package]:
        """Return the list of packages for this build"""
        return self.storage.get_packages(self.build.id)

    def get_path(self, item: Content) -> Path:
        """Return the path of the content type for this Build's storage"""
        return self.storage.get_path(self.build.id, item)

    @classmethod
    def purge(cls, machine: str):
        """Purge old builds for machine"""
        logging.info("Purging builds for %s", machine)
        build_dbs = BuildDB.builds(name=machine)
        purger = Purger(build_dbs, key=lambda b: b.submitted.replace(tzinfo=None))

        for build_db in purger.purge():  # type: BuildDB
            if not build_db.keep and not cls(build_db).published():
                buildman = cls(build_db)
                buildman.delete()

    @classmethod
    def search_notes(cls, machine: str, key: str) -> Iterator[BuildMan]:
        """search notes for given machine"""
        return (cls(build_db) for build_db in BuildDB.search_notes(machine, key))

    @staticmethod
    def diff_binpkgs(left: BuildMan, right: BuildMan) -> Iterator[Change]:
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
        return str(self.build)

    def __eq__(self, other) -> bool:
        return self.build == other.build


class MachineInfo:  # pylint: disable=too-few-public-methods
    """Data type for machine metadata

    Has the following attributes:

        name: str
        build_count: int
        latest_build: Optional[BuildMan]
        published: Optional[BuildMan]
    """

    def __init__(self, machine_name: str):
        latest_build = BuildDB.latest_build(machine_name)
        published = None

        if latest_build is not None:
            current_build = latest_build.number

            while current_build:
                buildman = BuildMan(Build(machine_name, current_build))
                if buildman.published():
                    published = buildman
                    break

                current_build -= 1

        self.name: str = machine_name
        self.build_count: int = BuildDB.count(machine_name)
        self.latest_build: Optional[BuildMan] = (
            BuildMan(latest_build) if latest_build else None
        )
        self.published: Optional[BuildMan] = published

    def builds(self) -> list[BuildMan]:
        """Return the builds for the given machine"""
        builddbs = BuildDB.builds(name=self.name)

        return [BuildMan(i) for i in builddbs]


def schedule_build(name: str) -> str:
    """Schedule a build on jenkins for the given machine name"""
    settings = Settings.from_environ()
    return schedule_jenkins_build(name, settings)


def diff_notes(left: BuildMan, right: BuildMan, header: str = "") -> str:
    """Return package diff as a string of notes

    If there are no changes, return an empty string
    """
    changeset = [
        item for item in BuildMan.diff_binpkgs(left, right) if item.status.is_a_build()
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
