"""
Django models for Gentoo Build Publisher
"""
from __future__ import annotations

from dataclasses import replace

from django.db import models

from gentoo_build_publisher.records import BuildRecord


class BuildModel(models.Model):
    """Django persistance for Build objects"""

    # The build's machine name
    machine = models.CharField(max_length=255, db_index=True)

    # The Jenkins build number
    build_id = models.CharField(max_length=255)

    # when this build was submitted to GBP
    submitted = models.DateTimeField()

    # When this build's publish task completed
    completed = models.DateTimeField(null=True)

    # When CI/CD build timestamp
    built = models.DateTimeField(null=True)

    keptbuild: KeptBuild
    buildnote: BuildNote
    buildlog: BuildLog

    class Meta:  # pylint: disable=too-few-public-methods,missing-class-docstring
        constraints = [
            models.UniqueConstraint(fields=["machine", "build_id"], name="unique_build")
        ]
        indexes = [
            models.Index(fields=["machine"]),
        ]
        verbose_name = "Build"
        verbose_name_plural = "Builds"

    def record(self) -> BuildRecord:
        """Convert BuildModel to BuildRecord"""
        record = BuildRecord(
            machine=self.machine,
            build_id=self.build_id,
            submitted=self.submitted,
            completed=self.completed,
            built=self.built,
        )
        try:
            record = replace(record, note=self.buildnote.note)
        except BuildNote.DoesNotExist:
            pass

        try:
            record = replace(record, logs=self.buildlog.logs)
        except BuildLog.DoesNotExist:
            pass

        try:
            self.keptbuild
        except KeptBuild.DoesNotExist:
            pass
        else:
            record = replace(record, keep=True)

        return record

    def __repr__(self) -> str:
        machine = self.machine
        build_id = self.build_id
        class_name = type(self).__name__

        return f"{class_name}(machine={machine!r}, build_id={build_id!r})"

    def __str__(self) -> str:
        return f"{self.machine}.{self.build_id}"


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
