"""DB interface for Gentoo Build Publisher"""
from __future__ import annotations

import datetime as dt
from typing import Any, Iterator, Optional, Type, TypeVar

from django.utils import timezone

from gentoo_build_publisher.build import Build
from gentoo_build_publisher.models import BuildLog, BuildModel, BuildNote, KeptBuild

T = TypeVar("T", bound="BuildDB")  # pylint: disable=invalid-name

RELATED = ("buildlog", "buildnote", "keptbuild")

ATTR_TO_1TO1 = {
    "keep": (KeptBuild, []),
    "logs": (BuildLog, ["logs"]),
    "note": (BuildNote, ["note"]),
    #  ^        ^           ^
    #  |        |           |
    #  |        |           + Fields to pass to the model's .upsert() method
    #  |        |
    #  |        +  Corresponding Django db model
    #  |
    #  + BuildDB attribute name
}


class BuildDB:
    """Abstraction of the Django ORM"""

    class NotFound(LookupError):
        """Not found exception for the .get() method"""

    def __init__(self, build_model: BuildModel):
        self.model = build_model

        try:
            self.note: Optional[str] = build_model.buildnote.note
        except BuildNote.DoesNotExist:
            self.note = None

        try:
            self.logs: Optional[str] = build_model.buildlog.logs
        except BuildLog.DoesNotExist:
            self.logs = None

        try:
            build_model.keptbuild
        except KeptBuild.DoesNotExist:
            self.keep = False
        else:
            self.keep = True

    @property
    def id(self) -> int:  # pylint: disable=invalid-name
        """Return the database id for this build"""
        return self.model.id

    @property
    def name(self) -> str:
        """Property for the Build name"""
        return self.model.name

    @name.setter
    def name(self, value: str):
        self.model.name = value

    @property
    def number(self) -> int:
        """Property for the Build number"""
        return self.model.number

    @number.setter
    def number(self, value: int):
        self.model.number = value

    @property
    def submitted(self) -> dt.datetime:
        """Property for the Build submitted timestamp"""
        return self.model.submitted

    @submitted.setter
    def submitted(self, value):
        self.model.submitted = value

    @property
    def completed(self) -> Optional[dt.datetime]:
        """Property for the Build completed timestamp"""
        return self.model.completed

    @completed.setter
    def completed(self, value: Optional[dt.datetime]):
        self.model.completed = value

    @property
    def task_id(self) -> Optional[str]:
        """Property for the Build's celery task id"""
        if self.model.task_id is None:
            return None

        return str(self.model.task_id)

    @task_id.setter
    def task_id(self, value: Optional[str]):
        self.model.task_id = value

    def refresh(self):
        """Refresh from the database"""
        self.model.refresh_from_db()
        self.__init__(self.model)

    def save(self):
        """Save changes back to the database"""
        self.model.submitted = self.submitted
        self.model.completed = self.completed
        self.model.task_id = self.task_id

        self.model.save()

        for attr, (model, fields) in ATTR_TO_1TO1.items():
            if getattr(self, attr):
                model.upsert(self.model, *[getattr(self, field) for field in fields])
            else:
                model.remove(self.model)  # bug with pylint: disable=no-member

    def delete(self):
        """Delete this Build from the db"""
        if self.model.pk is not None:
            self.model.delete()

    @classmethod
    def create(
        cls: Type[T], build: Build, submitted: Optional[dt.datetime] = None
    ) -> T:
        """Factory to create a db record.

        If the record already exists it will be returned unaltered.
        """
        if submitted is None:
            submitted = timezone.now()

        model, _ = BuildModel.objects.get_or_create(
            name=build.name, number=build.number, defaults={"submitted": submitted}
        )

        return cls(model)

    @classmethod
    def get(cls: Type[T], build: Build) -> T:
        """Factory to retrieve a db record.

        If the record does not exist in the database, cls.DoesNotExist is raised.
        """
        try:
            model = BuildModel.objects.select_related(*RELATED).get(
                name=build.name, number=build.number
            )
        except BuildModel.DoesNotExist as error:
            raise cls.NotFound from error

        return cls(model)

    @classmethod
    def get_or_create(cls: Type[T], build: Build) -> T:
        """Factory to retrieve a db record or create one if one doesn't exist"""
        try:
            return cls.get(build)
        except cls.NotFound:
            return cls.create(build)

    @classmethod
    def builds(cls, **filters) -> Iterator:
        """Query the datbase and return an iterable of BuildDB objects

        The order of the builds are by the submitted time, most recent first.

        For example:

            >>> BuildDB.builds(name="babette")
        """
        build_models = (
            BuildModel.objects.select_related(*RELATED)
            .filter(**filters)
            .order_by("-submitted")
        )

        return (cls(build_model) for build_model in build_models)

    @classmethod
    def list_machines(cls) -> list[str]:
        """Return a list of machine names"""
        machines = (
            BuildModel.objects.values_list("name", flat=True)
            .distinct()
            .order_by("name")
        )

        return list(machines)

    def previous_build(self, completed: bool = True) -> Optional[BuildDB]:
        """Return the previous build in the db or None"""
        if completed:
            query = BuildModel.objects.filter(
                name=self.name, completed__isnull=False, number__lt=self.number
            )
        else:
            query = BuildModel.objects.filter(name=self.name, number__lt=self.number)

        query = query.select_related(*RELATED).order_by("-number")

        try:
            build_model = query[0]
        except IndexError:
            return None

        return type(self)(build_model)

    def next_build(self, completed: bool = True) -> Optional[BuildDB]:
        """Return the next build in the db or None"""
        query = BuildModel.objects.filter(name=self.name, number__gt=self.number)

        if completed:
            query = query.filter(completed__isnull=False)

        query = query.select_related(*RELATED).order_by("number")

        try:
            build_model = query[0]
        except IndexError:
            return None

        return type(self)(build_model)

    @classmethod
    def latest_build(cls, name: str, completed: bool = False) -> Optional[BuildDB]:
        """Return the latest build for the given machine name.

        If `completed` is `True`, only consider completed builds.
        If no builds exist for the given machine name, return None.
        """
        filter_: dict[str, Any] = {"name": name}

        if completed:
            filter_["completed__isnull"] = False

        try:
            build_model = (
                BuildModel.objects.filter(**filter_)
                .order_by("-number")
                .select_related(*RELATED)
            )[0]
        except IndexError:
            return None

        return cls(build_model)

    @staticmethod
    def count(name: Optional[str] = None) -> int:
        """Return the total number of builds

        If `name` is given, return the total number of builds for the given machine
        """
        filter_: dict[str, Any] = {"name": name} if name else {}

        return BuildModel.objects.filter(**filter_).count()

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return NotImplemented

        return self.model == other.model

    def __hash__(self):
        return hash(self.model)

    def __repr__(self):
        return f"{type(self).__name__}({self.model!r})"
