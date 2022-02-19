"""DB interface for Gentoo Build Publisher"""
from __future__ import annotations

import datetime as dt
from dataclasses import InitVar, dataclass
from typing import Any, Iterator, TypeVar

from django.utils import timezone

from gentoo_build_publisher.build import BuildID
from gentoo_build_publisher.models import BuildLog, BuildModel, BuildNote, KeptBuild

T = TypeVar("T", bound="BuildDB")  # pylint: disable=invalid-name

RELATED = ("buildlog", "buildnote", "keptbuild")


@dataclass
class BuildRecord:
    """A Build record from the database"""

    build_id: InitVar[BuildID]
    note: str | None = None
    logs: str | None = None
    keep: bool = False
    submitted: dt.datetime | None = None
    completed: dt.datetime | None = None

    def __post_init__(self, build_id: BuildID):
        self._build_id = build_id

    @property
    def id(self) -> BuildID:  # pylint: disable=invalid-name
        """Return the BuildID associated with this record"""
        return self._build_id

    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}(build_id={self.id!r})"

    def __hash__(self) -> int:
        return hash(self.id)


class BuildDB:
    """Abstraction of the Django ORM"""

    class NotFound(LookupError):
        """Not found exception for the .get() method"""

    @classmethod
    def get(cls, build_id: BuildID) -> BuildRecord:
        """Retrieve db record"""
        try:
            build_model: BuildModel = BuildModel.objects.select_related(*RELATED).get(
                name=build_id.name, number=build_id.number
            )
        except BuildModel.DoesNotExist:
            raise cls.NotFound(build_id) from None

        return cls.model_to_record(build_model)

    @staticmethod
    def model_to_record(model: BuildModel) -> BuildRecord:
        """Convert BuildModel to BuildRecord"""
        record = BuildRecord(
            model.build_id, submitted=model.submitted, completed=model.completed
        )
        try:
            record.note = model.buildnote.note
        except BuildNote.DoesNotExist:
            pass

        try:
            record.logs = model.buildlog.logs
        except BuildLog.DoesNotExist:
            pass

        try:
            model.keptbuild
        except KeptBuild.DoesNotExist:
            pass
        else:
            record.keep = True

        return record

    @staticmethod
    def save(build_record: BuildRecord, **fields) -> BuildModel:
        """Save changes back to the database"""
        for name, value in fields.items():
            setattr(build_record, name, value)

        try:
            model: BuildModel = BuildModel.objects.get(
                name=build_record.id.name, number=build_record.id.number
            )
        except BuildModel.DoesNotExist:
            model = BuildModel(name=build_record.id.name, number=build_record.id.number)

        if build_record.submitted is None:
            build_record.submitted = timezone.now()

        model.submitted = build_record.submitted
        model.completed = build_record.completed

        model.save()

        KeptBuild.update(model, build_record.keep)
        BuildLog.update(model, build_record.logs)
        BuildNote.update(model, build_record.note)

        return model

    @staticmethod
    def delete(build_id: BuildID) -> None:
        """Delete this Build from the db"""
        BuildModel.objects.filter(name=build_id.name, number=build_id.number).delete()

    @staticmethod
    def exists(build_id: BuildID) -> bool:
        """Return True iff a record of the build exists in the database"""
        return BuildModel.objects.filter(
            name=build_id.name, number=build_id.number
        ).exists()

    @classmethod
    def get_records(cls, **filters) -> Iterator[BuildRecord]:
        """Query the datbase and return an iterable of BuildRecord objects

        The order of the builds are by the submitted time, most recent first.

        For example:

            >>> BuildDB.builds(name="babette")
        """
        models = (
            BuildModel.objects.select_related(*RELATED)
            .filter(**filters)
            .order_by("-submitted")
        )

        return (cls.model_to_record(model) for model in models)

    @staticmethod
    def list_machines() -> list[str]:
        """Return a list of machine names"""
        machines = (
            BuildModel.objects.values_list("name", flat=True)
            .distinct()
            .order_by("name")
        )

        return list(machines)

    @classmethod
    def previous_build(
        cls, build_id: BuildID, completed: bool = True
    ) -> BuildRecord | None:
        """Return the previous build in the db or None"""
        field_lookups = dict(name=build_id.name, number__lt=build_id.number)

        if completed:
            field_lookups["completed__isnull"] = False

        query = (
            BuildModel.objects.filter(**field_lookups)
            .select_related(*RELATED)
            .order_by("-number")
        )

        try:
            model = query[0]
        except IndexError:
            return None

        return cls.model_to_record(model)

    @classmethod
    def next_build(
        cls, build_id: BuildID, completed: bool = True
    ) -> BuildRecord | None:
        """Return the next build in the db or None"""
        field_lookups = dict(name=build_id.name, number__gt=build_id.number)

        if completed:
            field_lookups["completed__isnull"] = False

        query = (
            BuildModel.objects.filter(**field_lookups)
            .select_related(*RELATED)
            .order_by("number")
        )

        try:
            model = query[0]
        except IndexError:
            return None

        return cls.model_to_record(model)

    @classmethod
    def latest_build(cls, name: str, completed: bool = False) -> BuildRecord | None:
        """Return the latest build for the given machine name.

        If `completed` is `True`, only consider completed builds.
        If no builds exist for the given machine name, return None.
        """
        field_lookups: dict[str, Any] = {"name": name}

        if completed:
            field_lookups["completed__isnull"] = False

        try:
            model = (
                BuildModel.objects.filter(**field_lookups)
                .order_by("-number")
                .select_related(*RELATED)
            )[0]
        except IndexError:
            return None

        return cls.model_to_record(model)

    @classmethod
    def search_notes(cls, machine: str, key: str) -> Iterator[BuildRecord]:
        """search notes for given machine"""
        models = (
            BuildModel.objects.select_related(*RELATED)
            .filter(name=machine, buildnote__note__icontains=key)
            .order_by("-submitted")
        )

        return (cls.model_to_record(model) for model in models)

    @staticmethod
    def count(name: str | None = None) -> int:
        """Return the total number of builds

        If `name` is given, return the total number of builds for the given machine
        """
        field_lookups: dict[str, Any] = {"name": name} if name else {}

        return BuildModel.objects.filter(**field_lookups).count()
