"""
Django models for Gentoo Build Publisher
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from django.db import models

from gentoo_build_publisher import Build, Jenkins, Settings, Storage


class BuildModel(models.Model):
    """Django persistance for Build objects"""

    # The Jenkins build name
    name = models.CharField(max_length=255, db_index=True)

    # The Jenkins build number
    number = models.PositiveIntegerField()

    # when this build was submitted to GBP
    submitted = models.DateTimeField()

    # When this build's publish task completed
    completed = models.DateTimeField(null=True)

    # The build's task id
    task_id = models.UUIDField(null=True)

    keptbuild: KeptBuild

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        constraints = [
            models.UniqueConstraint(fields=["name", "number"], name="unique_build")
        ]
        indexes = [
            models.Index(fields=["name"]),
        ]
        verbose_name = "Build"
        verbose_name_plural = "Builds"

    def __init__(
        self,
        *args,
        jenkins: Optional[Jenkins] = None,
        settings: Optional[Settings] = None,
        storage: Optional[Storage] = None,
        **kwargs,
    ):
        self.jenkins: Jenkins
        self.storage: Storage

        self.settings = settings or Settings.from_environ()
        self.jenkins = jenkins or Jenkins.from_settings(self.settings)
        self.storage = storage or Storage.from_settings(self.settings)

        super().__init__(*args, **kwargs)

        self.build = Build(self.name, self.number)

    def __repr__(self) -> str:
        name = self.name
        number = self.number
        class_name = type(self).__name__

        return f"{class_name}(name={name!r}, number={number})"

    def __str__(self) -> str:
        return str(self.build)

    def publish(self):
        """Publish the Build"""
        self.storage.publish(self.build, self.jenkins)

    def published(self) -> bool:
        """Return True if this Build is published"""
        return self.storage.published(self.build)

    def delete(self, using=None, keep_parents=False):
        # The reason to call super().delete() before removing the directories is if for
        # some reason super().delete() fails we don't want to delete the directories.
        super().delete(using=using, keep_parents=keep_parents)

        self.storage.delete_build(self.build)

    def as_dict(self) -> Dict[str, Any]:
        """Convert build instance attributes to a dict"""
        data = {
            "name": self.name,
            "note": None,
            "number": self.number,
            "published": self.published(),
            "url": str(self.jenkins.build_url(self.build)),
            "submitted": self.submitted.isoformat(),
            "completed": self.completed.isoformat()
            if self.completed is not None
            else None,
        }

        try:
            data["note"] = self.buildnote.note  # pylint: disable=no-member
        except BuildNote.DoesNotExist:
            pass

        return data


class KeptBuild(models.Model):
    """BuildModels that we want to keep"""

    build_model = models.OneToOneField(
        BuildModel,
        on_delete=models.CASCADE,
        primary_key=True,
        db_column="id",
    )

    @classmethod
    def keep(cls, build_model: BuildModel) -> bool:
        """Return True if KeptBuild record exists for the given build_model"""
        try:
            cls.objects.get(build_model=build_model)
            return True
        except cls.DoesNotExist:
            return False

    def __str__(self) -> str:
        return str(self.build_model)


class BuildNote(models.Model):
    """Notes on a build"""

    build_model = models.OneToOneField(BuildModel, on_delete=models.CASCADE)
    note = models.TextField()

    def __str__(self) -> str:
        return f"Notes for build {self.build_model}"


class BuildLog(models.Model):
    """The Jenkins logs for a build"""

    build_model = models.OneToOneField(BuildModel, on_delete=models.CASCADE)
    logs = models.TextField()
