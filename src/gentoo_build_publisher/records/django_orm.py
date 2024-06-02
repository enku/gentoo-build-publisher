"""Django ORM records implementation"""

import datetime as dt
from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from django.conf import settings
from django.db import models

import gentoo_build_publisher._django_setup  # pylint: disable=unused-import
from gentoo_build_publisher.models import ApiKey as ApiKeyModel
from gentoo_build_publisher.models import BuildLog, BuildModel, BuildNote, KeptBuild
from gentoo_build_publisher.records import BuildRecord, RecordNotFound
from gentoo_build_publisher.types import ApiKey, Build
from gentoo_build_publisher.utils import decode, decrypt, encode, encrypt

RELATED = ("buildlog", "buildnote", "keptbuild")


class RecordDB:
    """Implements the RecordDB Protocol using Django's ORM as a backing store"""

    # What fields we implement .search() for
    searchable_fields = ["logs", "note"]

    @staticmethod
    def save(build_record: BuildRecord, **fields: Any) -> BuildRecord:
        """Save changes back to the database"""
        build_record = replace(build_record, **fields)

        try:
            model = BuildModel.objects.get(
                machine=build_record.machine, build_id=build_record.build_id
            )
        except BuildModel.DoesNotExist:
            model = BuildModel(
                machine=build_record.machine, build_id=build_record.build_id
            )

        submitted = build_record.submitted or dt.datetime.now(tz=dt.UTC)
        build_record = replace(build_record, submitted=submitted)
        model.submitted = submitted
        model.completed = build_record.completed
        model.built = build_record.built

        model.save()

        KeptBuild.update(model, build_record.keep)
        BuildLog.update(model, build_record.logs)
        BuildNote.update(model, build_record.note)

        return build_record

    @staticmethod
    def get(build: Build) -> BuildRecord:
        """Retrieve db record"""
        if isinstance(build, BuildRecord):
            return build

        try:
            build_model: BuildModel = BuildModel.objects.select_related(*RELATED).get(
                machine=build.machine, build_id=build.build_id
            )
        except BuildModel.DoesNotExist:
            raise RecordNotFound from None

        return build_model.record()

    @staticmethod
    def for_machine(machine: str) -> Iterable[BuildRecord]:
        """Return BuildRecords for the given machine"""
        build_models = (
            BuildModel.objects.select_related(*RELATED)
            .filter(machine=machine)
            .order_by(models.F("built").desc(nulls_last=True), "-submitted")
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

    def previous(
        self, build: BuildRecord, completed: bool = True
    ) -> BuildRecord | None:
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
            build_model: BuildModel = query[0]
        except IndexError:
            return None

        return build_model.record()

    def next(self, build: BuildRecord, completed: bool = True) -> BuildRecord | None:
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
            build_model: BuildModel = query[0]
        except IndexError:
            return None

        return build_model.record()

    @staticmethod
    def latest(machine: str, completed: bool = False) -> BuildRecord | None:
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
            build_model: BuildModel = (
                BuildModel.objects.filter(**field_lookups)
                .order_by(order_by)
                .select_related(*RELATED)
            )[0]
        except IndexError:
            return None

        return build_model.record()

    @classmethod
    def search(cls, machine: str, field: str, key: str) -> Iterable[BuildRecord]:
        """search the given field for given machine

        field must be a BuildRecord field. Not all fields may be searchable, in which
        case ValueError is raised.
        """
        if field not in cls.searchable_fields:
            raise ValueError(f"{field} is not a searchable field")

        field_filter = {
            "logs": "buildlog__logs__icontains",
            "note": "buildnote__note__icontains",
        }.get(field, f"{field}__icontains")

        build_models = (
            BuildModel.objects.select_related(*RELATED)
            .filter(**{"machine": machine, field_filter: key})
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


class ApiKeyDB:
    """Implements the ApiKeyDB Protocol using Django's ORM as a backing store"""

    def list(self) -> list[ApiKey]:
        """Return the list of ApiKeys"""
        return [
            ApiKey(
                name=obj.name,
                key=decode(decrypt(obj.apikey, encode(settings.SECRET_KEY))),
                created=obj.created,
                last_used=obj.last_used,
            )
            for obj in ApiKeyModel.objects.all().order_by("name")
        ]

    def get(self, name: str) -> ApiKey:
        """Retrieve db record"""
        model = self.get_model(name)

        return ApiKey(
            name=model.name,
            key=decode(decrypt(model.apikey, encode(settings.SECRET_KEY))),
            created=model.created,
        )

    def save(self, api_key: ApiKey) -> None:
        """Save the given ApiKey to the db"""
        obj = ApiKeyModel.objects.get_or_create(name=api_key.name)[0]
        obj.apikey = encrypt(encode(api_key.key), encode(settings.SECRET_KEY))
        obj.created = api_key.created
        obj.last_used = api_key.last_used
        obj.save()

    def delete(self, name: str) -> None:
        """Delete the ApiKey with the given name

        Raise RecordNotFound if it doesn't exist in the db
        """
        self.get_model(name).delete()

    def get_model(self, name: str) -> ApiKeyModel:
        """Return the ApiKeyModel with the given name

        Raise RecordNotFound if it doesn't exist in the db
        """
        try:
            return ApiKeyModel.objects.get(name=name)
        except ApiKeyModel.DoesNotExist:
            raise RecordNotFound from None
