"""The Publisher

When we think about a "build" In Gentoo Build Publisher there are three subsystems that,
when combined, represent the the build:

    * Jenkins: the connection to the Jenkins instance as well as the artifacts it hosts
    * Storage: the file system storage responsible where artifacts are pulled and
      extracted and eventually hosted by GBP.
    * Repo: Database repository holding various data not held in Storage

The above all classes (or Protocols) that operate independently.  There exists a facade
for these subsystems. This is the BuildPublisher.  For example, when a build is pulled,
then BuildPublisher.pull(build) ensures the artifact gets pull from Jenkins, get's
extracted into Storage, and appropriate metadata is created in the RecordDB.  Likewise
when a build is deleted (BuildPublisher.delete(build)) then it makes sure that the
Storage and Record are removed.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime
from difflib import Differ
from typing import Any, Iterable, Self

from gentoo_build_publisher.jenkins import Jenkins, JenkinsMetadata
from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.records import BuildRecord, RecordNotFound, Repo
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.signals import dispatcher
from gentoo_build_publisher.storage import Storage
from gentoo_build_publisher.types import (
    Build,
    Change,
    ChangeState,
    GBPMetadata,
    Package,
    PackageMetadata,
)
from gentoo_build_publisher.utils.time import utctime

logger = logging.getLogger(__name__)


class BuildPublisher:
    """Pulls a build's db, jenkins and storage all together"""

    def __init__(self, *, jenkins: Jenkins, storage: Storage, repo: Repo):
        self.jenkins = jenkins
        self.storage = storage
        self.repo = repo

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        """Instantiate from settings"""
        jenkins = Jenkins.from_settings(settings)
        storage = Storage.from_settings(settings)
        repo = Repo.from_settings(settings)

        return cls(jenkins=jenkins, storage=storage, repo=repo)

    def record(self, build: Build) -> BuildRecord:
        """Return BuildRecord for this build.

        If we already have one, return it.
        Otherwise if a record exists in the RecordDB, get it from the RecordDB.
        Otherwise create an "empty" record.
        """
        if isinstance(build, BuildRecord):
            return build

        try:
            return self.repo.build_records.get(build)
        except RecordNotFound:
            return BuildRecord(build.machine, build.build_id)

    def save(self, record: BuildRecord, **fields: Any) -> BuildRecord:
        """Save the build or record to the records repository"""
        return self.repo.build_records.save(record, **fields)

    def publish(self, build: Build) -> None:
        """Publish the build"""
        if not self.pulled(build):
            self.pull(build)

        self.storage.publish(build)
        dispatcher.emit("published", build=self.record(build))

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

    def pull(
        self,
        build: Build,
        *,
        note: str | None = None,
        tags: Iterable[str] | None = None,
    ) -> bool:
        """pull the Build to storage

        If the given build has already been pulled, nothing is pulled.
        Otherwise if `note` is given, then the build record will be saved with the given
        note.
        Likewise, if `tags` is given then the given tags will be assigned to the Build.
        """
        if self.pulled(build):
            return False

        record = self.record(build)
        record = self.save(record, submitted=record.submitted or utctime(), note=note)
        logger.info("Pulling build: %s", build)

        # Ensure we only send the Build on pre-pull because the Record a) is incomplete
        # and b) may get deleted if the pull fails
        dispatcher.emit("prepull", build=Build(build.machine, build.build_id))

        self.storage.extract_artifact(
            build,
            self.jenkins.download_artifact(build),
            self.repo.build_records.previous(record),
        )

        logger.info("Pulled build %s", build)

        for tag in tags or []:
            self.tag(build, tag)

        record, packages, gbp_metadata = self._update_build_metadata(record)

        dispatcher.emit(
            "postpull", build=record, packages=packages, gbp_metadata=gbp_metadata
        )

        return True

    def _update_build_metadata(
        self, record: BuildRecord
    ) -> tuple[BuildRecord, list[Package] | None, GBPMetadata | None]:
        packages: list[Package] | None = None
        gbp_metadata: GBPMetadata | None = None
        jenkins_metadata = self.jenkins.get_metadata(record)
        built = utctime(datetime.utcfromtimestamp(jenkins_metadata.timestamp / 1000))
        logs = self.jenkins.get_logs(record)
        record = self.save(record, logs=logs, completed=utctime(), built=built)

        try:
            packages = self.storage.get_packages(record)
        except LookupError:
            pass
        else:
            gbp_metadata = self.gbp_metadata(jenkins_metadata, packages)
            self.storage.set_metadata(record, gbp_metadata)

        return record, packages, gbp_metadata

    def pulled(self, build: Build) -> bool:
        """Return true if the Build has been pulled"""
        return self.storage.pulled(build) and self.record(build).completed is not None

    def delete(self, build: Build) -> None:
        """Delete this build"""
        dispatcher.emit("predelete", build=build)
        self.repo.build_records.delete(build)
        self.storage.delete(build)
        dispatcher.emit("postdelete", build=build)

    def get_packages(self, build: Build) -> list[Package]:
        """Return the list of packages for this build"""
        return self.storage.get_packages(build)

    def schedule_build(self, machine: str, **params: Any) -> str | None:
        """Schedule a build on jenkins for the given machine name"""
        return self.jenkins.schedule_build(machine, **params)

    def search(self, machine: str, field: str, key: str) -> list[BuildRecord]:
        """search the given field on the given machine"""
        return list(self.repo.build_records.search(machine, field, key))

    def diff_binpkgs(self, left: Build, right: Build) -> Iterable[Change]:
        """Compare two package's binpkgs and generate the differences"""
        if left == right:
            return

        left_packages = [f"{package.cpvb()}\n" for package in self.get_packages(left)]
        right_packages = [f"{package.cpvb()}\n" for package in self.get_packages(right)]
        code_map = {"-": "REMOVED", "+": "ADDED"}
        diff = Differ().compare(left_packages, right_packages)

        for item in diff:
            if change_state := code_map.get(item[0]):
                cpvb = item[2:].rstrip()
                yield Change(cpvb, ChangeState[change_state])

    def machines(self, *, names: Iterable[str] | None = None) -> list[MachineInfo]:
        """Return list of machines with metadata

        If names is given, only return machines who's names are contained.
        """

        machine_names = self.repo.build_records.list_machines()
        if names is not None:
            machine_names = [name for name in machine_names if name in set(names)]

        return [MachineInfo(i) for i in machine_names]

    def latest_build(self, machine: str, completed: bool = False) -> BuildRecord | None:
        """Return the latest completed build for the given machine name"""
        return self.repo.build_records.latest(machine, completed)

    @staticmethod
    def gbp_metadata(
        jenkins_metadata: JenkinsMetadata, packages: list[Package]
    ) -> GBPMetadata:
        """Generate GBPMetadata given JenkinsMetadata and Packages"""
        built: list[Package] = []
        jenkins_built_time = math.floor(jenkins_metadata.timestamp / 1000)
        total = len(packages)

        size = 0
        for package in packages:
            if package.build_time >= jenkins_built_time:
                built.append(package)
            size += package.size

        pkg_metadata = PackageMetadata(total=total, size=size, built=built)
        duration = jenkins_metadata.duration

        return GBPMetadata(build_duration=duration, packages=pkg_metadata)

    def build_metadata(self, build: Build) -> GBPMetadata:
        """Return the GBPMetadata for the given build.

        This uses the gbp.json from storage if available. If not available it is
        generated on-demand.
        """
        try:
            return self.storage.get_metadata(build)
        except LookupError:
            pass

        # Really old builds, or corrupt builds, don't have a gbp.json file. We can still
        # generate the GBPMetadata however.
        try:
            packages = self.storage.get_packages(build)
        except LookupError:
            packages = []

        # build_duration comes from Jenkins, but we may not have this build in Jenkins
        # anymore. Instead we calculate it (estimate) based on the BuildRecord. But only
        # for completed builds.
        build = self.record(build)
        timestamp, duration = (
            (
                build.built.timestamp() * 1000,
                (build.completed - build.built).total_seconds(),
            )
            if build.built and build.completed
            else (0, 0)
        )
        jenkins_metadata = JenkinsMetadata(int(duration), int(timestamp))

        return self.gbp_metadata(jenkins_metadata, packages)
