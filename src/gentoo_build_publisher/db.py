"""DB interface for Gentoo Build Publisher"""
from __future__ import annotations

import datetime as dt
from typing import Iterator, List, Optional, Type, TypeVar

from django.utils import timezone

from gentoo_build_publisher.build import Build
from gentoo_build_publisher.models import BuildLog, BuildModel, BuildNote, KeptBuild

T = TypeVar("T", bound="BuildDB")  # pylint: disable=invalid-name


class BuildDB:
    """Abstraction of the Django ORM"""

    class NotFound(LookupError):
        """Not found exception for the .get() method"""

    def __init__(self, build_model: BuildModel):
        self.model = build_model

        try:
            self.note: Optional[str] = BuildNote.objects.get(
                build_model=build_model
            ).note
        except BuildNote.DoesNotExist:
            self.note = None

        try:
            self.logs: Optional[str] = BuildLog.objects.get(
                build_model=build_model
            ).logs
        except BuildLog.DoesNotExist:
            self.logs = None

        try:
            KeptBuild.objects.get(build_model=build_model)
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

        if self.note:
            build_note, _ = BuildNote.objects.get_or_create(build_model=self.model)
            build_note.note = self.note
            build_note.save()
        else:
            try:
                build_note = BuildNote.objects.get(build_model=self.model)
            except BuildNote.DoesNotExist:
                pass
            else:
                build_note.delete()

        if self.logs:
            build_log, _ = BuildLog.objects.get_or_create(build_model=self.model)
            build_log.logs = self.logs
            build_log.save()
        else:
            try:
                build_log = BuildLog.objects.get(build_model=self.model)
            except BuildLog.DoesNotExist:
                pass
            else:
                build_log.delete()

        if self.keep:
            KeptBuild.objects.get_or_create(build_model=self.model)
        else:
            try:
                kept_build = KeptBuild.objects.get(build_model=self.model)
            except KeptBuild.DoesNotExist:
                pass
            else:
                kept_build.delete()

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
            model = BuildModel.objects.get(name=build.name, number=build.number)
        except BuildModel.DoesNotExist as error:
            raise cls.NotFound from error

        return cls(model)

    @classmethod
    def builds(cls, **filters) -> Iterator:
        """Query the datbase and return an iterable of BuildDB objects

        The order of the builds are by the submitted time, most recent first.

        For example:

            >>> BuildDB.builds(name="babette")
        """
        build_models = BuildModel.objects.filter(**filters).order_by("-submitted")

        return (cls(build_model) for build_model in build_models)

    @classmethod
    def list_machines(cls) -> List[str]:
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

        query = query.order_by("-number")

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

        query = query.order_by("number")

        try:
            build_model = query[0]
        except IndexError:
            return None

        return type(self)(build_model)

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return NotImplemented

        return self.model == other.model

    def __hash__(self):
        return hash(self.model)

    def __repr__(self):
        return f"{type(self).__name__}({self.model!r})"
