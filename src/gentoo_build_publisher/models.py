"""
Django models for Gentoo Build Publisher
"""
from __future__ import annotations

from typing import Type, TypeVar

from django.db import models

T = TypeVar("T")  # pylint: disable=invalid-name


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

    def __repr__(self) -> str:
        name = self.name
        number = self.number
        class_name = type(self).__name__

        return f"{class_name}(name={name!r}, number={number})"

    def __str__(self) -> str:
        return f"{self.name}.{self.number}"


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

    @classmethod
    def upsert(cls: Type[T], build_model: BuildModel, note_text: str) -> T:
        """Save the text for the build_model's note.

        Return the BuildNote instance.
        """
        build_note, _ = cls.objects.get_or_create(  # type: ignore
            build_model=build_model
        )
        build_note.note = note_text
        build_note.save()

        return build_note

    @classmethod
    def remove(cls, build_model: BuildModel) -> bool:
        """Delete note for build_model.

        Returns True if note was deleted.

        Returns False if there was no note to delete.
        """
        try:
            build_note = cls.objects.get(build_model=build_model)
        except cls.DoesNotExist:
            return False

        build_note.delete()

        return True

    def __str__(self) -> str:
        return f"Notes for build {self.build_model}"


class BuildLog(models.Model):
    """The Jenkins logs for a build"""

    build_model = models.OneToOneField(BuildModel, on_delete=models.CASCADE)
    logs = models.TextField()
