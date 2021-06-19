"""Managers"""
from datetime import datetime, timezone
from pathlib import PosixPath
from typing import Any, Dict, Optional, Union

from yarl import URL

from gentoo_build_publisher.build import Build, Content
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.diff import diff_notes
from gentoo_build_publisher.jenkins import JenkinsBuild
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.storage import StorageBuild

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
                "build argument must be one of [Build, BuildDB]"
            )  # pragma: no cover

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
        if self._db is None:
            try:
                self._db = BuildDB.get(self.build)
            except BuildDB.NotFound:
                self._db = BuildDB.create(self.build)

        if not self.storage_build.pulled():
            if previous_build_db := self.db.previous_build():
                previous_storage_build = type(self)(previous_build_db)
            else:
                previous_storage_build = None

            self.storage_build.extract_artifact(
                self.jenkins_build.download_artifact(),
                previous_build=previous_storage_build,
            )

        prev_build = BuildDB.previous_build(self.db)

        if prev_build is not None:
            binpkgs = Content.BINPKGS
            left = BuildMan(prev_build).get_path(binpkgs)
            right = self.get_path(binpkgs)
            note = diff_notes(str(left), str(right), header="Packages built:\n")

            if note:
                self.db.note = note

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

    def as_dict(self) -> Dict[str, Any]:
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
