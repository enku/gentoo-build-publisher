"""Resolvers for the GraphQL Query type"""

from typing import Any, TypeAlias

from ariadne import ObjectType
from graphql import GraphQLError, GraphQLResolveInfo

from gentoo_build_publisher import publisher, utils
from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.types import TAG_SYM, Build

Query = ObjectType("Query")
Info: TypeAlias = GraphQLResolveInfo
Object: TypeAlias = dict[str, Any]

# pylint: disable=redefined-builtin,invalid-name
# pylint: disable=missing-function-docstring


@Query.field("machines")
def machines(
    _obj: Any, _info: Info, names: list[str] | None = None
) -> list[MachineInfo]:
    return publisher.machines(names=names)


@Query.field("build")
def build(_obj: Any, _info: Info, id: str) -> Build | None:
    _build = Build.from_id(id)

    return None if not publisher.repo.build_records.exists(_build) else _build


@Query.field("latest")
def latest(_obj: Any, _info: Info, machine: str) -> BuildRecord | None:
    return publisher.latest_build(machine, completed=True)


@Query.field("builds")
def builds(_obj: Any, _info: Info, machine: str) -> list[BuildRecord]:
    return [
        record
        for record in publisher.repo.build_records.for_machine(machine)
        if record.completed
    ]


@Query.field("diff")
def diff(_obj: Any, _info: Info, left: str, right: str) -> Object | None:
    left_build = Build.from_id(left)

    if not publisher.repo.build_records.exists(left_build):
        raise GraphQLError(f"Build does not exist: {left}")

    right_build = Build.from_id(right)

    if not publisher.repo.build_records.exists(right_build):
        raise GraphQLError(f"Build does not exist: {right}")

    items = publisher.diff_binpkgs(left_build, right_build)

    return {"left": left_build, "right": right_build, "items": list(items)}


@Query.field("search")
def search(
    _obj: Any, _info: Info, machine: str, field: str, key: str
) -> list[BuildRecord]:
    search_field = {"NOTES": "note", "LOGS": "logs"}[field]

    return publisher.search(machine, search_field, key)


@Query.field("searchNotes")
def searchnotes(_obj: Any, _info: Info, machine: str, key: str) -> list[BuildRecord]:
    return publisher.search(machine, "note", key)


@Query.field("version")
def version(_obj: Any, _info: Info) -> str:
    return utils.get_version()


@Query.field("working")
def working(_obj: Any, _info: Info) -> list[BuildRecord]:
    return [
        record
        for machine in publisher.repo.build_records.list_machines()
        for record in publisher.repo.build_records.for_machine(machine)
        if not record.completed
    ]


@Query.field("resolveBuildTag")
def resolvebuildtag(_obj: Any, _info: Info, machine: str, tag: str) -> Build | None:
    try:
        return publisher.storage.resolve_tag(f"{machine}{TAG_SYM}{tag}")
    except FileNotFoundError:
        return None
