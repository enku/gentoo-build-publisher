"""GraphQL resolvers for Gentoo Build Publisher"""
# Most of the functions are resolvers and need no explanation
# pylint: disable=missing-function-docstring

# "id" is used throughout. It's idiomatic GraphQL
# pylint: disable=redefined-builtin,invalid-name
from __future__ import annotations

import datetime as dt
from functools import cached_property
from importlib import resources
from typing import Any, Optional

from ariadne import (
    EnumType,
    ObjectType,
    gql,
    make_executable_schema,
    snake_case_fallback_resolvers,
)
from ariadne_django.scalars import datetime_scalar
from graphql import GraphQLError

from gentoo_build_publisher.publisher import MachineInfo, get_publisher
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.tasks import publish_build, pull_build
from gentoo_build_publisher.types import Build, Package, Status
from gentoo_build_publisher.utils import get_version

Object = dict[str, Any]
type_defs = gql(resources.read_text("gentoo_build_publisher", "schema.graphql"))
resolvers = [
    EnumType("StatusEnum", Status),
    datetime_scalar,
    ObjectType("Build"),
    ObjectType("MachineSummary"),
    mutation := ObjectType("Mutation"),
    query := ObjectType("Query"),
]


class GQLBuild:
    """Build Type resolvers"""

    def __init__(self, build: Build):

        self.build = build
        self._record = build if isinstance(build, BuildRecord) else None

    def id(self, _) -> str:
        return self.build.id

    def machine(self, _) -> str:
        return self.build.machine

    def keep(self, _) -> bool:
        return self.record.keep

    def built(self, _) -> dt.datetime | None:
        return self.record.built

    def submitted(self, _) -> dt.datetime | None:
        return self.record.submitted

    def completed(self, _) -> dt.datetime | None:
        return self.record.completed

    def logs(self, _) -> str | None:
        return self.record.logs

    def notes(self, _) -> str | None:
        return self.record.note

    @cached_property
    def published(self) -> bool:
        publisher = get_publisher()

        return publisher.published(self.build)

    @cached_property
    def pulled(self) -> bool:
        publisher = get_publisher()

        return publisher.pulled(self.build)

    @cached_property
    def packages(self) -> list[str] | None:
        publisher = get_publisher()

        if not publisher.pulled(self.build):
            return None

        try:
            return [package.cpv for package in publisher.get_packages(self.build)]
        except LookupError:
            return None

    @cached_property
    def packages_built(self) -> list[Package] | None:
        publisher = get_publisher()

        try:
            gbp_metadata = publisher.storage.get_metadata(self.build)
        except LookupError as error:
            raise GraphQLError("Packages built unknown") from error

        return gbp_metadata.packages.built

    @cached_property
    def record(self) -> BuildRecord:
        publisher = get_publisher()

        if self._record is None:
            self._record = publisher.record(self.build)

        return self._record


@query.field("machines")
def resolve_query_machines(*_) -> list[MachineInfo]:
    publisher = get_publisher()

    return publisher.machines()


@query.field("build")
def resolve_query_build(*_, id: str) -> Optional[GQLBuild]:
    publisher = get_publisher()
    build = Build(id)

    return None if not publisher.records.exists(build) else GQLBuild(build)


@query.field("latest")
def resolve_query_latest(*_, machine: str) -> Optional[GQLBuild]:
    publisher = get_publisher()
    record = publisher.latest_build(machine, completed=True)

    return None if record is None else GQLBuild(record)


@query.field("builds")
def resolve_query_builds(*_, machine: str) -> list[GQLBuild]:
    publisher = get_publisher()

    records = publisher.records.query(machine=machine, completed__isnull=False)

    return [GQLBuild(record) for record in records]


@query.field("diff")
def resolve_query_diff(*_, left: str, right: str) -> Optional[Object]:
    publisher = get_publisher()
    left_build = Build(left)

    if not publisher.records.exists(left_build):
        return None

    right_build = Build(right)

    if not publisher.records.exists(right_build):
        return None

    items = publisher.diff_binpkgs(left_build, right_build)

    return {
        "left": GQLBuild(left_build),
        "right": GQLBuild(right_build),
        "items": [*items],
    }


@query.field("searchNotes")
def resolve_query_searchnotes(*_, machine: str, key: str) -> list[GQLBuild]:
    publisher = get_publisher()

    return [GQLBuild(i) for i in publisher.search_notes(machine, key)]


@query.field("version")
def resolve_query_version(*_) -> str:
    return get_version()


@query.field("working")
def resolve_query_working(*_) -> list[GQLBuild]:
    publisher = get_publisher()
    records = publisher.records.query(completed=None)

    return [GQLBuild(record) for record in records]


@mutation.field("publish")
def resolve_mutation_publish(*_, id: str) -> MachineInfo:
    publisher = get_publisher()
    build = Build(id)

    if publisher.pulled(build):
        publisher.publish(build)
    else:
        publish_build.delay(build.id)

    return MachineInfo(build.machine)


@mutation.field("pull")
def resolve_mutation_pull(*_, id: str) -> MachineInfo:
    build = Build(id)

    pull_build.delay(id)

    return MachineInfo(build.machine)


@mutation.field("scheduleBuild")
def resolve_mutation_schedule_build(*_, machine: str) -> str:
    publisher = get_publisher()

    return publisher.schedule_build(machine)


@mutation.field("keepBuild")
def resolve_mutation_keepbuild(*_, id: str) -> Optional[GQLBuild]:
    publisher = get_publisher()
    build = Build(id)

    if not publisher.records.exists(build):
        return None

    record = publisher.record(build)
    publisher.records.save(record, keep=True)

    return GQLBuild(record)


@mutation.field("releaseBuild")
def resolve_mutation_releasebuild(*_, id: str) -> Optional[GQLBuild]:
    publisher = get_publisher()
    build = Build(id)

    if not publisher.records.exists(build):
        return None

    record = publisher.record(build)
    publisher.records.save(record, keep=False)

    return GQLBuild(record)


@mutation.field("createNote")
def resolve_mutation_createnote(
    *_, id: str, note: Optional[str] = None
) -> Optional[GQLBuild]:
    publisher = get_publisher()
    build = Build(id)

    if not publisher.records.exists(build):
        return None

    record = publisher.record(build)
    publisher.records.save(record, note=note)

    return GQLBuild(record)


schema = make_executable_schema(type_defs, resolvers, snake_case_fallback_resolvers)
