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
from ariadne.contrib.django.scalars import datetime_scalar
from graphql.type.definition import GraphQLResolveInfo

from gentoo_build_publisher import diff
from gentoo_build_publisher.build import Build, Content
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.managers import BuildMan, MachineInfo
from gentoo_build_publisher.tasks import publish_build

Object = dict[str, Any]
type_defs = gql(resources.read_text("gentoo_build_publisher", "schema.graphql"))
resolvers = [
    EnumType("StatusEnum", diff.Status),
    datetime_scalar,
    build := ObjectType("Build"),
    machine_summary := ObjectType("MachineSummary"),
    mutation := ObjectType("Mutation"),
    query := ObjectType("Query"),
]

build.set_field("keep", lambda build_man, _: build_man.db.keep)
build.set_field("submitted", lambda build_man, _: build_man.db.submitted)
build.set_field("completed", lambda build_man, _: build_man.db.completed)
build.set_field("logs", lambda build_man, _: build_man.db.logs)
build.set_field("notes", lambda build_man, _: build_man.db.note)
build.set_field("published", lambda build_man, _: build_man.published())
build.set_field("pulled", lambda build_man, _: build_man.pulled())


@build.field("packages")
def resolve_build_packages(build_man: BuildMan, _) -> Optional[list[str]]:
    if not build_man.pulled():
        return None

    try:
        return build_man.get_packages()
    except LookupError:
        return None


machine_summary.set_alias("builds", "build_count")
machine_summary.set_alias("publishedBuild", "published")


@query.field("machines")
def resolve_query_machines(*_) -> list[MachineInfo]:
    return [MachineInfo(name) for name in BuildDB.list_machines()]


@query.field("build")
def resolve_query_build(*_, name: str, number: int) -> Optional[BuildMan]:
    build_man = BuildMan(Build(name=name, number=number))
    return None if build_man.db is None else build_man


@query.field("latest")
def resolve_query_latest(*_, name: str) -> Optional[BuildMan]:
    build_db = BuildDB.latest_build(name, completed=True)
    return None if build_db is None else BuildMan(build_db)


@query.field("builds")
def resolve_query_builds(*_, name: str) -> list[BuildMan]:
    build_dbs = BuildDB.builds(name=name, completed__isnull=False)
    build_mans = [BuildMan(build_db) for build_db in build_dbs]
    return build_mans


@query.field("diff")
def resolve_query_diff(*_, left: Object, right: Object) -> Optional[Object]:
    left_build = BuildMan(Build(name=left["name"], number=left["number"]))
    right_build = BuildMan(Build(name=right["name"], number=right["number"]))

    if not (left_build.db and right_build.db):
        return None

    left_path = left_build.storage_build.get_path(Content.BINPKGS)
    right_path = right_build.storage_build.get_path(Content.BINPKGS)

    items = diff.dirdiff(str(left_path), str(right_path))

    return {"left": left_build, "right": right_build, "items": [*items]}


@query.field("packages")
def resolve_query_packages(
    _, info: GraphQLResolveInfo, name: str, number: int
) -> Optional[list[str]]:
    build_man = BuildMan(Build(name=name, number=number))
    return resolve_build_packages(build_man, info)


@mutation.field("publish")
def resolve_mutation_publish(*_, name: str, number: int) -> MachineInfo:
    build_man = BuildMan(Build(name=name, number=number))

    if build_man.pulled():
        build_man.publish()
    else:
        publish_build.delay(name, number)

    return MachineInfo(name)


schema = make_executable_schema(type_defs, resolvers, snake_case_fallback_resolvers)
