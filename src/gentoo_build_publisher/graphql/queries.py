"""Resolvers for the GraphQL Query type"""

from typing import Any

from ariadne import ObjectType
from graphql import GraphQLError, GraphQLResolveInfo

from gentoo_build_publisher import plugins, publisher, utils
from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.stats import Stats
from gentoo_build_publisher.types import TAG_SYM, Build

type Info = GraphQLResolveInfo
type Object = dict[str, Any]

QUERY = ObjectType("Query")
TAG_INFO = ObjectType("TagInfo")

# pylint: disable=redefined-builtin,missing-function-docstring


@QUERY.field("machines")
def machines(
    _obj: Any, _info: Info, names: list[str] | None = None
) -> list[MachineInfo]:
    return publisher.machines(names=names)


@QUERY.field("build")
def build(_obj: Any, _info: Info, id: str) -> Build | None:
    build_ = Build.from_id(id)

    return None if not publisher.repo.build_records.exists(build_) else build_


@QUERY.field("latest")
def latest(_obj: Any, _info: Info, machine: str) -> BuildRecord | None:
    return publisher.latest_build(machine, completed=True)


@QUERY.field("builds")
def builds(_obj: Any, _info: Info, machine: str) -> list[BuildRecord]:
    return [
        record
        for record in publisher.repo.build_records.for_machine(machine)
        if record.completed
    ]


@QUERY.field("diff")
def diff(_obj: Any, _info: Info, left: str, right: str) -> Object | None:
    left_build = Build.from_id(left)

    if not publisher.repo.build_records.exists(left_build):
        raise GraphQLError(f"Build does not exist: {left}")

    right_build = Build.from_id(right)

    if not publisher.repo.build_records.exists(right_build):
        raise GraphQLError(f"Build does not exist: {right}")

    items = publisher.diff_binpkgs(left_build, right_build)

    return {"left": left_build, "right": right_build, "items": list(items)}


@QUERY.field("search")
def search(
    _obj: Any, _info: Info, machine: str, field: str, key: str
) -> list[BuildRecord]:
    search_field = {"NOTES": "note", "LOGS": "logs"}[field]

    return publisher.search(machine, search_field, key)


@QUERY.field("searchNotes")
def search_notes(_obj: Any, _info: Info, machine: str, key: str) -> list[BuildRecord]:
    return publisher.search(machine, "note", key)


@QUERY.field("version")
def version(_obj: Any, _info: Info) -> str:
    return utils.get_version()


@QUERY.field("working")
def working(_obj: Any, _info: Info) -> list[BuildRecord]:
    return [
        record
        for machine in publisher.repo.build_records.list_machines()
        for record in publisher.repo.build_records.for_machine(machine)
        if not record.completed
    ]


@QUERY.field("resolveBuildTag")
def resolve_build_tag(_obj: Any, _info: Info, machine: str, tag: str) -> Build | None:
    return publisher.resolve_tag(f"{machine}{TAG_SYM}{tag}")


@QUERY.field("plugins")
def get_plugins(_obj: Any, _info: Info) -> list[plugins.Plugin]:
    return plugins.get_plugins()


@QUERY.field("stats")
def stats(_obj: Any, _info: Info) -> Stats:
    return Stats.with_cache()


@TAG_INFO.field("build")
def tag_build(context: dict[str, Any], _info: Info) -> Build | None:
    return publisher.resolve_tag(f"{context['machine']}{TAG_SYM}{context['tag']}")
