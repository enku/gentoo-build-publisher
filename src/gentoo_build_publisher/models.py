"""
Django models for Gentoo Build Publisher
"""
from __future__ import annotations

from typing import Type, TypeVar

from django.db import models

T = TypeVar("T", bound=models.Model)  # pylint: disable=invalid-name


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

    @classmethod
    def upsert(cls: Type[T], build_model: BuildModel) -> T:
        """Get or create a KeptBuild for the given build_model

        Return the KeptBuild instance.
        """
        return upsert_1to1(cls, build_model)

    @classmethod
    def remove(cls, build_model: BuildModel) -> bool:
        """Delete KeptBuild for build_model.

        Returns True if KeptBuild was deleted.

        Returns False if there was no KeptBuild to delete.
        """
        return remove_1to1(cls, build_model)

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
        return upsert_1to1(cls, build_model, note=note_text)

    @classmethod
    def remove(cls, build_model: BuildModel) -> bool:
        """Delete note for build_model.

        Returns True if note was deleted.

        Returns False if there was no note to delete.
        """
        return remove_1to1(cls, build_model)

    def __str__(self) -> str:
        return f"Notes for build {self.build_model}"


class BuildLog(models.Model):
    """The Jenkins logs for a build"""

    build_model = models.OneToOneField(BuildModel, on_delete=models.CASCADE)
    logs = models.TextField()

    @classmethod
    def upsert(cls: Type[T], build_model: BuildModel, logs: str) -> T:
        """Save the text for the build_model's logs.

        Return the BuildLog instance.
        """
        return upsert_1to1(cls, build_model, logs=logs)

    @classmethod
    def remove(cls, build_model: BuildModel) -> bool:
        """Delete log for build_model

        Returns True if log was deleted.

        Returns False if there was no log to delete.
        """
        return remove_1to1(cls, build_model)


def upsert_1to1(model: Type[T], build_model: BuildModel, **attrs) -> T:
    """Save the attrs for the build_model's Model.

    Return the Model instance.
    """
    obj = model.objects.get_or_create(build_model=build_model)[0]  # type: ignore

    for field, value in attrs.items():
        setattr(obj, field, value)
    obj.save()

    return obj


def remove_1to1(model: Type[T], build_model: BuildModel) -> bool:
    """Delete model for build_model.

    Returns True if model was deleted.

    Returns False if there was no model to delete.
    """
    try:
        obj = model.objects.get(build_model=build_model)
    except model.DoesNotExist:
        return False

    obj.delete()

    return True
