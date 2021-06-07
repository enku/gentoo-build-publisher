"""Managers"""
from pathlib import PosixPath
from typing import Any, Dict, Optional, Union

from django.utils import timezone
from yarl import URL

from gentoo_build_publisher import Build, JenkinsBuild, Settings, Storage
from gentoo_build_publisher.models import BuildModel, BuildNote


class BuildMan:
    """Pulls a build's db model, jenkins and storage all together"""

    def __init__(
        self,
        build: Union[Build, BuildModel],
        *,
        jenkins_build: Optional[JenkinsBuild] = None,
        storage: Optional[Storage] = None
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

        if storage is None:
            self.storage = Storage.from_settings(Settings.from_environ())
        else:
            self.storage = storage

    @property
    def id(self):  # pylint: disable=invalid-name
        """Return the BuildModel id or None if there is no model"""
        return self.model.id if self.model is not None else None

    def publish(self):
        """Publish the build"""
        if self.model is None:
            self.model, _ = BuildModel.objects.get_or_create(
                name=self.name,
                number=self.number,
                defaults={"submitted": timezone.now()},
            )
        self.storage.publish(self.build, self.jenkins_build)

    def published(self) -> bool:
        """Return True if this Build is published"""
        return self.storage.published(self.build)

    def pull(self):
        """pull the Build to storage"""
        if self.model is None:
            self.model, _ = BuildModel.objects.get_or_create(
                name=self.name,
                number=self.number,
                defaults={"submitted": timezone.now()},
            )
        return self.storage.pull(self.build, self.jenkins_build)

    def pulled(self) -> bool:
        """Return true if the Build has been pulled"""
        return self.storage.pulled(self.build)

    def delete(self):
        """Delete this build"""
        if self.model is not None:
            self.model.delete()

        self.storage.delete_build(self.build)

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
        return self.storage.get_path(self.build, item)
