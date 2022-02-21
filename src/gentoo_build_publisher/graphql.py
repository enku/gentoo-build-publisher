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

from .managers import BuildPublisher, MachineInfo
from .tasks import publish_build, pull_build
from .types import Build, BuildID, BuildRecord, Package, Status
from .utils import get_version

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

        self.build_publisher = BuildPublisher()

    def id(self, _) -> str:
        return str(self.build.id)

    def machine(self, _) -> str:
        return self.build.name

    def keep(self, _) -> bool:
        return self.record.keep

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
        return self.build_publisher.published(self.build)

    @cached_property
    def pulled(self) -> bool:
        return self.build_publisher.pulled(self.build)

    @cached_property
    def packages(self) -> list[str] | None:
        if not self.build_publisher.pulled(self.build):
            return None

        try:
            return [
                package.cpv for package in self.build_publisher.get_packages(self.build)
            ]
        except LookupError:
            return None

    @cached_property
    def packages_built(self) -> list[Package] | None:
        try:
            gbp_metadata = self.build_publisher.storage.get_metadata(self.build)
        except LookupError as error:
            raise GraphQLError("Packages built unknown") from error

        return gbp_metadata.packages.built

    @cached_property
    def record(self) -> BuildRecord:
        if self._record is None:
            self._record = self.build_publisher.record(self.build)

        return self._record


@query.field("machines")
def resolve_query_machines(*_) -> list[MachineInfo]:
    build_publisher = BuildPublisher()

    return build_publisher.machines()


@query.field("build")
def resolve_query_build(*_, id: str) -> Optional[GQLBuild]:
    build_publisher = BuildPublisher()
    build_id = BuildID(id)

    return (
        None
        if build_publisher.record(build_id).completed is None
        else GQLBuild(build_id)
    )


@query.field("latest")
def resolve_query_latest(*_, name: str) -> Optional[GQLBuild]:
    build_publisher = BuildPublisher()
    record = build_publisher.latest_build(name, completed=True)

    return None if record is None else GQLBuild(record)


@query.field("builds")
def resolve_query_builds(*_, name: str) -> list[GQLBuild]:
    records = BuildPublisher().records

    build_records = records.query(name=name, completed__isnull=False)

    return [GQLBuild(record) for record in build_records]


@query.field("diff")
def resolve_query_diff(*_, left: str, right: str) -> Optional[Object]:
    build_publisher = BuildPublisher()
    left_build_id = BuildID(left)

    if not build_publisher.records.exists(left_build_id):
        return None

    right_build_id = BuildID(right)

    if not build_publisher.records.exists(right_build_id):
        return None

    items = build_publisher.diff_binpkgs(left_build_id, right_build_id)

    return {
        "left": GQLBuild(left_build_id),
        "right": GQLBuild(right_build_id),
        "items": [*items],
    }


@query.field("searchNotes")
def resolve_query_searchnotes(*_, name: str, key: str) -> list[GQLBuild]:
    build_publisher = BuildPublisher()

    return [GQLBuild(i) for i in build_publisher.search_notes(name, key)]


@query.field("version")
def resolve_query_version(*_) -> str:
    return get_version()


@query.field("working")
def resolve_query_working(*_) -> list[GQLBuild]:
    records = BuildPublisher().records

    build_records = records.query(completed=None)

    return [GQLBuild(record) for record in build_records]


@mutation.field("publish")
def resolve_mutation_publish(*_, id: str) -> MachineInfo:
    build_id = BuildID(id)
    build_publisher = BuildPublisher()

    if build_publisher.pulled(build_id):
        build_publisher.publish(build_id)
    else:
        publish_build.delay(str(build_id))

    return MachineInfo(build_id.name)


@mutation.field("pull")
def resolve_mutation_pull(*_, id: str) -> MachineInfo:
    pull_build.delay(id)

    name = id.partition(".")[0]

    return MachineInfo(name)


@mutation.field("scheduleBuild")
def resolve_mutation_schedule_build(*_, name: str) -> str:
    build_publisher = BuildPublisher()

    return build_publisher.schedule_build(name)


@mutation.field("keepBuild")
def resolve_mutation_keepbuild(*_, id: str) -> Optional[GQLBuild]:
    build_id = BuildID(id)
    build_publisher = BuildPublisher()

    if not build_publisher.records.exists(build_id):
        return None

    record = build_publisher.record(build_id)
    build_publisher.records.save(record, keep=True)

    return GQLBuild(record)


@mutation.field("releaseBuild")
def resolve_mutation_releasebuild(*_, id: str) -> Optional[GQLBuild]:
    build_id = BuildID(id)
    build_publisher = BuildPublisher()

    if not build_publisher.records.exists(build_id):
        return None

    record = build_publisher.record(build_id)
    build_publisher.records.save(record, keep=False)

    return GQLBuild(record)


@mutation.field("createNote")
def resolve_mutation_createnote(
    *_, id: str, note: Optional[str] = None
) -> Optional[GQLBuild]:
    build_id = BuildID(id)
    build_publisher = BuildPublisher()

    if not build_publisher.records.exists(build_id):
        return None

    record = build_publisher.record(build_id)
    build_publisher.records.save(record, note=note)

    return GQLBuild(record)


schema = make_executable_schema(type_defs, resolvers, snake_case_fallback_resolvers)
