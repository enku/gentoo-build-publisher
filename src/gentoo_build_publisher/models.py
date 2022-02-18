"""
Django models for Gentoo Build Publisher
"""
from __future__ import annotations

from django.db import models


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
    def update(cls, build_model: BuildModel, keep: bool) -> None:
        """Get or create a KeptBuild for the given build_model"""
        if keep:
            cls.objects.get_or_create(build_model=build_model)
        else:
            cls.objects.filter(build_model=build_model).delete()

    def __str__(self) -> str:
        return str(self.build_model)


class BuildNote(models.Model):
    """Notes on a build"""

    build_model = models.OneToOneField(BuildModel, on_delete=models.CASCADE)
    note = models.TextField()

    @classmethod
    def update(cls, build_model: BuildModel, note_text: str | None) -> None:
        """Save or remove the text for the build_model's note"""
        if note_text is not None:
            cls.objects.update_or_create(
                build_model=build_model, defaults={"note": note_text}
            )
        else:
            cls.objects.filter(build_model=build_model).delete()

    def __str__(self) -> str:
        return f"Notes for build {self.build_model}"


class BuildLog(models.Model):
    """The Jenkins logs for a build"""

    build_model = models.OneToOneField(BuildModel, on_delete=models.CASCADE)
    logs = models.TextField()

    @classmethod
    def update(cls, build_model: BuildModel, logs: str | None) -> None:
        """Save or remove the text for the build_model's logs"""
        if logs is not None:
            cls.objects.update_or_create(
                build_model=build_model, defaults={"logs": logs}
            )
        else:
            cls.objects.filter(build_model=build_model).delete()
