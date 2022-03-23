"""
Django models for Gentoo Build Publisher
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from django.db import models
from django.utils import timezone

from gentoo_build_publisher.records import BuildRecord, RecordNotFound
from gentoo_build_publisher.types import Build

RELATED = ("buildlog", "buildnote", "keptbuild")


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
            str(self),
            submitted=self.submitted,
            completed=self.completed,
            built=self.built,
        )
        try:
            record.note = self.buildnote.note
        except BuildNote.DoesNotExist:
            pass

        try:
            record.logs = self.buildlog.logs
        except BuildLog.DoesNotExist:
            pass

        try:
            self.keptbuild
        except KeptBuild.DoesNotExist:
            pass
        else:
            record.keep = True

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


class RecordDB:
    """Implements the RecordDB Protocol"""

    @staticmethod
    def save(build_record: BuildRecord, **fields) -> None:
        """Save changes back to the database"""
        for name, value in fields.items():
            setattr(build_record, name, value)

        try:
            model = BuildModel.objects.get(
                machine=build_record.machine, build_id=build_record.build_id
            )
        except BuildModel.DoesNotExist:
            model = BuildModel(
                machine=build_record.machine, build_id=build_record.build_id
            )

        if build_record.submitted is None:
            build_record.submitted = timezone.now()

        model.submitted = build_record.submitted
        model.completed = build_record.completed
        model.built = build_record.built

        model.save()

        KeptBuild.update(model, build_record.keep)
        BuildLog.update(model, build_record.logs)
        BuildNote.update(model, build_record.note)

    @staticmethod
    def get(build: Build) -> BuildRecord:
        """Retrieve db record"""
        if isinstance(build, BuildRecord):
            return build

        try:
            build_model = BuildModel.objects.select_related(*RELATED).get(
                machine=build.machine, build_id=build.build_id
            )
        except BuildModel.DoesNotExist:
            raise RecordNotFound from None

        return build_model.record()

    @staticmethod
    def query(**filters) -> Iterable[BuildRecord]:
        """Query the datbase and return an iterable of BuildRecord objects

        The order of the builds are by the submitted time, most recent first.

        For example:

            >>> BuildDB.builds(machine="babette")
        """
        build_models = (
            BuildModel.objects.select_related(*RELATED)
            .filter(**filters)
            .order_by("-submitted")
        )

        return (build_model.record() for build_model in build_models)

    @staticmethod
    def for_machine(machine: str) -> Iterable[BuildRecord]:
        """Return BuildRecords for the given machine"""
        build_models = (
            BuildModel.objects.select_related(*RELATED)
            .filter(machine=machine)
            .order_by("-submitted")
        )

        return (build_model.record() for build_model in build_models)

    @staticmethod
    def delete(build: Build) -> None:
        """Delete this Build from the db"""
        BuildModel.objects.filter(
            machine=build.machine, build_id=build.build_id
        ).delete()

    @staticmethod
    def exists(build: Build) -> bool:
        """Return True iff a record of the build exists in the database"""
        return BuildModel.objects.filter(
            machine=build.machine, build_id=build.build_id
        ).exists()

    @staticmethod
    def list_machines() -> list[str]:
        """Return a list of machine names"""
        machines = (
            BuildModel.objects.values_list("machine", flat=True)
            .distinct()
            .order_by("machine")
        )

        return list(machines)

    @staticmethod
    def previous(build: BuildRecord, completed: bool = True) -> BuildRecord | None:
        """Return the previous build in the db or None"""
        field_lookups: dict[str, Any] = {
            "built__isnull": False,
            "machine": build.machine,
        }

        if build.built:
            field_lookups["built__lt"] = build.built

        if completed:
            field_lookups["completed__isnull"] = False

        query = (
            BuildModel.objects.filter(**field_lookups)
            .select_related(*RELATED)
            .order_by("-built")
        )

        try:
            build_model = query[0]
        except IndexError:
            return None

        return build_model.record()

    @staticmethod
    def next_build(build: BuildRecord, completed: bool = True) -> BuildRecord | None:
        """Return the next build in the db or None"""
        field_lookups: dict[str, Any] = {"machine": build.machine}

        if build.built:
            field_lookups["built__gt"] = build.built

        if completed:
            field_lookups["completed__isnull"] = False

        query = (
            BuildModel.objects.filter(**field_lookups)
            .select_related(*RELATED)
            .order_by("built")
        )

        try:
            build_model = query[0]
        except IndexError:
            return None

        return build_model.record()

    @staticmethod
    def latest_build(machine: str, completed: bool = False) -> BuildRecord | None:
        """Return the latest build for the given machine name.

        If `completed` is `True`, only consider completed builds.
        If no builds exist for the given machine name, return None.
        """
        field_lookups: dict[str, Any] = {"machine": machine}

        if completed:
            field_lookups["completed__isnull"] = False

        if BuildModel.objects.filter(**field_lookups, built__isnull=False).count():
            field_lookups["built__isnull"] = False
            order_by = "-built"
        else:
            order_by = "-build_id"  # backwards compat

        try:
            build_model = (
                BuildModel.objects.filter(**field_lookups)
                .order_by(order_by)
                .select_related(*RELATED)
            )[0]
        except IndexError:
            return None

        return build_model.record()

    @staticmethod
    def search_notes(machine: str, key: str) -> Iterable[BuildRecord]:
        """search notes for given machine"""
        build_models = (
            BuildModel.objects.select_related(*RELATED)
            .filter(machine=machine, buildnote__note__icontains=key)
            .order_by("-submitted")
        )

        return (build_model.record() for build_model in build_models)

    @staticmethod
    def count(machine: str | None = None) -> int:
        """Return the total number of builds

        If `machine` is given, return the total number of builds for the given machine
        """
        field_lookups: dict[str, Any] = {"machine": machine} if machine else {}

        return BuildModel.objects.filter(**field_lookups).count()
