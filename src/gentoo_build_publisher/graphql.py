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
from gentoo_build_publisher.managers import BuildMan, MachineInfo
from gentoo_build_publisher.tasks import publish_build, pull_build
from gentoo_build_publisher.utils import get_version

Object = dict[str, Any]
type_defs = gql(resources.read_text("gentoo_build_publisher", "schema.graphql"))
resolvers = [
    EnumType("StatusEnum", Status),
    datetime_scalar,
    build := ObjectType("Build"),
    machine_summary := ObjectType("MachineSummary"),
    mutation := ObjectType("Mutation"),
    query := ObjectType("Query"),
]

build.set_field("name", lambda build_man, _: build_man.id.name)
build.set_field("number", lambda build_man, _: build_man.id.number)
build.set_field("keep", lambda build_man, _: build_man.record.keep)
build.set_field("submitted", lambda build_man, _: build_man.record.submitted)
build.set_field("completed", lambda build_man, _: build_man.record.completed)
build.set_field("logs", lambda build_man, _: build_man.record.logs)
build.set_field("notes", lambda build_man, _: build_man.record.note)
build.set_field("published", lambda build_man, _: build_man.published())
build.set_field("pulled", lambda build_man, _: build_man.pulled())


@build.field("packages")
def resolve_build_packages(build_man: BuildMan, _) -> Optional[list[str]]:
    if not build_man.pulled():
        return None

    try:
        return [package.cpv for package in build_man.get_packages()]
    except LookupError:
        return None


@build.field("packagesBuilt")
def resolve_build_packagesbuilt(build_man: BuildMan, _) -> Optional[list[Package]]:
    try:
        gbp_metadata = build_man.storage.get_metadata(build_man.id)
    except LookupError as error:
        raise GraphQLError("Packages built unknown") from error

    return gbp_metadata.packages.built


machine_summary.set_alias("publishedBuild", "published")


@machine_summary.field("builds")
def resolve_machinesummary_builds(machine_info: MachineInfo, _) -> list[BuildMan]:
    return machine_info.builds()


@query.field("machines")
def resolve_query_machines(*_) -> list[MachineInfo]:
    return [MachineInfo(name) for name in BuildDB.list_machines()]


@query.field("build")
def resolve_query_build(*_, name: str, number: int) -> Optional[BuildMan]:
    build_id = BuildID.create(name, number)
    build_man = BuildMan(build_id)
    return None if build_man.record is None else build_man


@query.field("latest")
def resolve_query_latest(*_, name: str) -> Optional[BuildMan]:
    build_db = BuildDB.latest_build(name, completed=True)
    return None if build_db is None else BuildMan(build_db)


@query.field("builds")
def resolve_query_builds(*_, name: str) -> list[BuildMan]:
    records = BuildDB.get_records(name=name, completed__isnull=False)
    build_mans = [BuildMan(record) for record in records]
    return build_mans


@query.field("diff")
def resolve_query_diff(*_, left: Object, right: Object) -> Optional[Object]:
    left_build_id = BuildID.create(left["name"], left["number"])
    left_build = BuildMan(left_build_id)

    if not left_build.record:
        return None

    right_build_id = BuildID.create(right["name"], right["number"])
    right_build = BuildMan(right_build_id)

    if not right_build.record:
        return None

    items = BuildMan.diff_binpkgs(left_build, right_build)

    return {"left": left_build, "right": right_build, "items": [*items]}


@query.field("searchNotes")
def resolve_query_searchnotes(*_, name: str, key: str) -> list[BuildMan]:
    return [*BuildMan.search_notes(name, key)]


@query.field("version")
def resolve_query_version(*_) -> str:
    return get_version()


@query.field("working")
def resolve_query_working(*_) -> list[BuildMan]:
    records = BuildDB.get_records(completed=None)

    return [BuildMan(record) for record in records]


@mutation.field("publish")
def resolve_mutation_publish(*_, name: str, number: int) -> MachineInfo:
    build_id = BuildID.create(name, number)
    build_man = BuildMan(build_id)

    if build_man.pulled():
        build_man.publish()
    else:
        publish_build.delay(name, number)

    return MachineInfo(name)


@mutation.field("pull")
def resolve_mutation_pull(*_, name: str, number: int) -> MachineInfo:
    pull_build.delay(name, number)
    return MachineInfo(name)


@mutation.field("scheduleBuild")
def resolve_mutation_schedule_build(*_, name: str) -> str:
    return BuildMan.schedule_build(name)


@mutation.field("keepBuild")
def resolve_mutation_keepbuild(*_, name: str, number: int) -> Optional[BuildMan]:
    build_id = BuildID.create(name, number)
    build_man = BuildMan(build_id)

    if not build_man.record:
        return None

    build_man.record.keep = True
    BuildDB.save(build_man.record)

    return build_man


@mutation.field("releaseBuild")
def resolve_mutation_releasebuild(*_, name: str, number: int) -> Optional[BuildMan]:
    build_id = BuildID.create(name, number)
    build_man = BuildMan(build_id)

    if not build_man.record:
        return None

    build_man.record.keep = False
    BuildDB.save(build_man.record)

    return build_man


@mutation.field("createNote")
def resolve_mutation_createnote(
    *_, name: str, number: int, note: Optional[str] = None
) -> Optional[BuildMan]:
    build_id = BuildID.create(name, number)
    build_man = BuildMan(build=build_id)

    if not build_man.record:
        return None

    build_man.record.note = note
    build_man.save_record()

    return build_man


schema = make_executable_schema(type_defs, resolvers, snake_case_fallback_resolvers)
