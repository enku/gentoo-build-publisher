"""GraphQL resolvers for Gentoo Build Publisher"""
# Most of the functions are resolvers and need no explanation
# pylint: disable=missing-function-docstring
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

from gentoo_build_publisher.build import BuildID, Package, Status
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import Build, MachineInfo
from gentoo_build_publisher.tasks import publish_build, pull_build
from gentoo_build_publisher.utils import get_version

Object = dict[str, Any]
type_defs = gql(resources.read_text("gentoo_build_publisher", "schema.graphql"))
resolvers = [
    EnumType("StatusEnum", Status),
    datetime_scalar,
    build_type := ObjectType("Build"),
    machine_summary := ObjectType("MachineSummary"),
    mutation := ObjectType("Mutation"),
    query := ObjectType("Query"),
]

build_type.set_field("name", lambda build, _: build.id.name)
build_type.set_field("number", lambda build, _: build.id.number)
build_type.set_field("keep", lambda build, _: build.record.keep)
build_type.set_field("submitted", lambda build, _: build.record.submitted)
build_type.set_field("completed", lambda build, _: build.record.completed)
build_type.set_field("logs", lambda build, _: build.record.logs)
build_type.set_field("notes", lambda build, _: build.record.note)
build_type.set_field("published", lambda build, _: build.published())
build_type.set_field("pulled", lambda build, _: build.pulled())


@build_type.field("packages")
def resolve_build_packages(build: Build, _) -> Optional[list[str]]:
    if not build.pulled():
        return None

    try:
        return [package.cpv for package in build.get_packages()]
    except LookupError:
        return None


@build_type.field("packagesBuilt")
def resolve_build_packagesbuilt(build: Build, _) -> Optional[list[Package]]:
    try:
        gbp_metadata = build.storage.get_metadata(build.id)
    except LookupError as error:
        raise GraphQLError("Packages built unknown") from error

    return gbp_metadata.packages.built


machine_summary.set_alias("publishedBuild", "published")


@machine_summary.field("builds")
def resolve_machinesummary_builds(machine_info: MachineInfo, _) -> list[Build]:
    return machine_info.builds()


@query.field("machines")
def resolve_query_machines(*_) -> list[MachineInfo]:
    return [MachineInfo(name) for name in BuildDB.list_machines()]


@query.field("build")
def resolve_query_build(*_, name: str, number: int) -> Optional[Build]:
    build_id = BuildID.create(name, number)
    build = Build(build_id)
    return None if build.record is None else build


@query.field("latest")
def resolve_query_latest(*_, name: str) -> Optional[Build]:
    build_db = BuildDB.latest_build(name, completed=True)
    return None if build_db is None else Build(build_db)


@query.field("builds")
def resolve_query_builds(*_, name: str) -> list[Build]:
    records = BuildDB.get_records(name=name, completed__isnull=False)
    builds = [Build(record) for record in records]
    return builds


@query.field("diff")
def resolve_query_diff(*_, left: Object, right: Object) -> Optional[Object]:
    left_build_id = BuildID.create(left["name"], left["number"])
    left_build = Build(left_build_id)

    if not left_build.record:
        return None

    right_build_id = BuildID.create(right["name"], right["number"])
    right_build = Build(right_build_id)

    if not right_build.record:
        return None

    items = Build.diff_binpkgs(left_build, right_build)

    return {"left": left_build, "right": right_build, "items": [*items]}


@query.field("searchNotes")
def resolve_query_searchnotes(*_, name: str, key: str) -> list[Build]:
    return [*Build.search_notes(name, key)]


@query.field("version")
def resolve_query_version(*_) -> str:
    return get_version()


@query.field("working")
def resolve_query_working(*_) -> list[Build]:
    records = BuildDB.get_records(completed=None)

    return [Build(record) for record in records]


@mutation.field("publish")
def resolve_mutation_publish(*_, name: str, number: int) -> MachineInfo:
    build_id = BuildID.create(name, number)
    build = Build(build_id)

    if build.pulled():
        build.publish()
    else:
        publish_build.delay(str(build_id))

    return MachineInfo(name)


@mutation.field("pull")
def resolve_mutation_pull(*_, name: str, number: int) -> MachineInfo:
    pull_build.delay(f"{name}.{number}")
    return MachineInfo(name)


@mutation.field("scheduleBuild")
def resolve_mutation_schedule_build(*_, name: str) -> str:
    return Build.schedule_build(name)


@mutation.field("keepBuild")
def resolve_mutation_keepbuild(*_, name: str, number: int) -> Optional[Build]:
    build_id = BuildID.create(name, number)
    build = Build(build_id)

    if not build.record:
        return None

    build.record.keep = True
    BuildDB.save(build.record)

    return build


@mutation.field("releaseBuild")
def resolve_mutation_releasebuild(*_, name: str, number: int) -> Optional[Build]:
    build_id = BuildID.create(name, number)
    build = Build(build_id)

    if not build.record:
        return None

    build.record.keep = False
    BuildDB.save(build.record)

    return build


@mutation.field("createNote")
def resolve_mutation_createnote(
    *_, name: str, number: int, note: Optional[str] = None
) -> Optional[Build]:
    build_id = BuildID.create(name, number)
    build = Build(build=build_id)

    if not build.record:
        return None

    build.record.note = note
    build.save_record()

    return build


schema = make_executable_schema(type_defs, resolvers, snake_case_fallback_resolvers)
