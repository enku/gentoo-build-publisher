"""Managers"""
from pathlib import PosixPath
from typing import Any, Dict, Optional, Union

from django.utils import timezone
from yarl import URL

from gentoo_build_publisher import Build, JenkinsBuild, Settings, StorageBuild
from gentoo_build_publisher.models import BuildModel, BuildNote


class BuildMan:
    """Pulls a build's db model, jenkins and storage all together"""

    def __init__(
        self,
        build: Union[Build, BuildModel],
        *,
        jenkins_build: Optional[JenkinsBuild] = None,
        storage_build: Optional[StorageBuild] = None
    ):
        if isinstance(build, Build):
            self.build = build
            self.model: Optional[BuildModel] = None
        elif isinstance(build, BuildModel):
            self.build = Build(name=build.name, number=build.number)
            self.model = build
        else:
            raise TypeError(
                "build argument must be one of [Build, BuildModel]"
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
        """Return the BuildModel id or None if there is no model"""
        return self.model.id if self.model is not None else None

    def publish(self):
        """Publish the build"""
        self.pull()
        self.storage_build.publish()

    def published(self) -> bool:
        """Return True if this Build is published"""
        return self.storage_build.published()

    def pull(self):
        """pull the Build to storage"""
        if self.model is None:
            self.model, _ = BuildModel.objects.get_or_create(
                name=self.name,
                number=self.number,
                defaults={"submitted": timezone.now()},
            )

        if not self.storage_build.pulled():
            self.storage_build.extract_artifact(self.jenkins_build.download_artifact())

    def pulled(self) -> bool:
        """Return true if the Build has been pulled"""
        return self.storage_build.pulled()

    def delete(self):
        """Delete this build"""
        if self.model is not None:
            self.model.delete()

        self.storage_build.delete()

    def as_dict(self) -> Dict[str, Any]:
        """Convert build instance attributes to a dict"""
        submitted: Optional[str] = None
        completed: Optional[str] = None
        note: Optional[str] = None

        if self.model is not None:
            submitted = self.model.submitted.isoformat()
            completed = (
                self.model.completed.isoformat()
                if self.model.completed is not None
                else None
            )

            try:
                note = self.model.buildnote.note  # pylint: disable=no-member
            except BuildNote.DoesNotExist:
                pass

        return {
            "name": self.name,
            "note": note,
            "number": self.number,
            "published": self.published(),
            "url": str(self.jenkins_build.artifact_url()),
            "submitted": submitted,
            "completed": completed,
        }

    def logs_url(self) -> URL:
        """Return the JenkinsBuild logs url for this Build"""
        return self.jenkins_build.logs_url()

    def get_path(self, item: Build.Content) -> PosixPath:
        """Return the path of the content type for this Build's storage"""
        return self.storage_build.get_path(item)
