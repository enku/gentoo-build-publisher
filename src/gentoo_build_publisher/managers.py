"""Managers"""
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import PosixPath
from typing import Any, Optional, Union

from yarl import URL

from gentoo_build_publisher import io
from gentoo_build_publisher.build import Build, Content
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.diff import diff_notes
from gentoo_build_publisher.jenkins import JenkinsBuild
from gentoo_build_publisher.purge import Purger
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import StorageBuild

logger = logging.getLogger(__name__)
utcnow = datetime.utcnow


class BuildMan:
    """Pulls a build's db, jenkins and storage all together"""

    def __init__(
        self,
        build: Union[Build, BuildDB],
        *,
        jenkins_build: Optional[JenkinsBuild] = None,
        storage_build: Optional[StorageBuild] = None,
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

        if storage_build is None:
            self.storage_build = StorageBuild.from_settings(
                self.build, Settings.from_environ()
            )
        else:
            self.storage_build = storage_build

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

        self.storage_build.publish()

    def published(self) -> bool:
        """Return True if this Build is published"""
        return self.storage_build.published()

    def pull(self):
        """pull the Build to storage"""
        if self.pulled():
            return

        build = self.build
        storage = self.storage_build
        jenkins = self.jenkins_build

        self._db = self._db or BuildDB.get_or_create(build)
        previous_build_db = BuildDB.previous_build(self._db)

        if previous_build_db:
            previous_build_storage = type(self)(previous_build_db)
        else:
            previous_build_storage = None

        logger.info("Pulling build: %s", build)

        chunk_size = jenkins.jenkins.download_chunk_size
        with tempfile.TemporaryFile(buffering=chunk_size) as temp:
            logger.info("Downloading build: %s", build)
            io.write_chunks(temp, jenkins.download_artifact())

            logger.info("Downloaded build: %s", build)
            temp.seek(0)

            byte_stream = io.read_chunks(temp, chunk_size)
            storage.extract_artifact(byte_stream, previous_build_storage)

        logging.info("Pulled build %s", build)

        self.update_build_metadata(previous_build_db)

    def update_build_metadata(self, previous_build_db: Optional[BuildDB] = None):
        """Update the build's db attributes (based on storage, etc.)"""
        self._db = self._db or BuildDB.get_or_create(self.build)

        if previous_build_db:
            binpkgs = Content.BINPKGS
            left = BuildMan(previous_build_db).get_path(binpkgs)
            right = self.get_path(binpkgs)
            self.db.note = diff_notes(str(left), str(right), header="Packages built:\n")

        self.db.logs = self.jenkins_build.get_logs()
        self.db.completed = utcnow().replace(tzinfo=timezone.utc)
        self.db.save()

    def pulled(self) -> bool:
        """Return true if the Build has been pulled"""
        return self.storage_build.pulled()

    def delete(self):
        """Delete this build"""
        if self.db is not None:
            self.db.delete()

        self.storage_build.delete()

    def as_dict(self) -> dict[str, Any]:
        """Convert build instance attributes to a dict"""
        if self.db is not None:
            db_dict = {
                "submitted": self.db.submitted.isoformat(),
                "completed": (
                    self.db.completed.isoformat()
                    if self.db.completed is not None
                    else None
                ),
                "note": self.db.note,
                "keep": self.db.keep,
            }
        else:
            db_dict = {}

        return {
            "name": self.name,
            "number": self.number,
            "storage": {
                "published": self.published(),
                "pulled": self.pulled(),
            },
            "db": db_dict,
            "jenkins": {
                "url": str(self.jenkins_build.artifact_url()),
            },
        }

    def logs_url(self) -> URL:
        """Return the JenkinsBuild logs url for this Build"""
        return self.jenkins_build.logs_url()

    def get_path(self, item: Content) -> PosixPath:
        """Return the path of the content type for this Build's storage"""
        return self.storage_build.get_path(item)

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

    def as_dict(self) -> dict[str, Any]:
        """Return dataclass as a dictionary"""
        latest_build: Optional[dict] = None
        published: Optional[dict] = None

        if self.latest_build:
            latest_build = {
                "number": self.latest_build.number,
                "submitted": self.latest_build.db.submitted,
            }

        if self.published:
            published = {
                "number": self.published.number,
                "submitted": self.published.db.submitted,
            }

        return {
            "builds": self.build_count,
            "latest_build": latest_build,
            "name": self.name,
            "published": published,
        }
