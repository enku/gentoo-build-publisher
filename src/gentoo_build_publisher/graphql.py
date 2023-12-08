"""GraphQL resolvers for Gentoo Build Publisher"""
# Most of the functions are resolvers and need no explanation
# pylint: disable=missing-function-docstring

# "id" is used throughout. It's idiomatic GraphQL
# pylint: disable=redefined-builtin,invalid-name
from __future__ import annotations

import datetime as dt
import importlib.metadata
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property, wraps
from importlib import resources
from typing import Any

from ariadne import (
    EnumType,
    ObjectType,
    gql,
    make_executable_schema,
    snake_case_fallback_resolvers,
)
from ariadne_django.scalars import datetime_scalar
from graphql import GraphQLError, GraphQLResolveInfo

from gentoo_build_publisher import jobs
from gentoo_build_publisher.common import TAG_SYM, Build, Package, Status
from gentoo_build_publisher.publisher import BuildPublisher, MachineInfo
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.utils import get_version

LOCALHOST = "127.0.0.1", "::1", "localhost"
SCHEMA_GROUP = "gentoo_build_publisher.graphql_schema"

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


Resolver = Callable[..., Any]


def load_schema() -> tuple[list[str], list[ObjectType]]:
    """Load all GraphQL schema for Gentoo Build Publisher

    This function loads all entry points for the group
    "gentoo_build_publisher.graphql_schema" and returns them all into a single list.
    This list can be used to make_executable_schema()
    """
    all_type_defs: list[str] = []
    all_resolvers = []

    for entry_point in importlib.metadata.entry_points(group=SCHEMA_GROUP):
        module = entry_point.load()
        all_type_defs.append(module.type_defs)
        all_resolvers.extend(module.resolvers)

    return (all_type_defs, all_resolvers)


def require_localhost(fn: Resolver) -> Resolver:
    """require localhost on this resolver"""

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        """type annotation"""
        info: GraphQLResolveInfo = args[1]
        environ = info.context["request"].environ
        client_ip = (
            (
                environ.get("HTTP_FORWARD", "")
                or environ.get("HTTP_X_FORWARDED_FOR", "")
                or environ.get("REMOTE_ADDR", "")
            )
            .split(",", 1)[0]
            .strip()
        )

        if client_ip not in LOCALHOST:
            raise GraphQLError(f"Unauthorized to resolve {info.path.key}")
        return fn(args[0], info, *args[2:], **kwargs)

    return wrapper


@dataclass(frozen=True, slots=True)
class Error:
    """Return Type for errors"""

    message: str

    @classmethod
    def from_exception(cls, exception: Exception) -> Error:
        return cls(f"{exception.__class__.__name__}: {exception}")


class BuildProxy:
    """Build Type resolvers"""

    def __init__(self, build: Build):
        self.build = build
        self._record = build if isinstance(build, BuildRecord) else None

    def id(self, _info: GraphQLResolveInfo) -> str:
        return self.build.id

    def machine(self, _info: GraphQLResolveInfo) -> str:
        return self.build.machine

    def keep(self, _info: GraphQLResolveInfo) -> bool:
        return self.record.keep

    def built(self, _info: GraphQLResolveInfo) -> dt.datetime | None:
        return self.record.built

    def submitted(self, _info: GraphQLResolveInfo) -> dt.datetime | None:
        return self.record.submitted

    def completed(self, _info: GraphQLResolveInfo) -> dt.datetime | None:
        return self.record.completed

    def logs(self, _info: GraphQLResolveInfo) -> str | None:
        return self.record.logs

    def notes(self, _info: GraphQLResolveInfo) -> str | None:
        return self.record.note

    @cached_property
    def published(self) -> bool:
        publisher = BuildPublisher.get_publisher()

        return publisher.published(self.build)

    @cached_property
    def tags(self) -> list[str]:
        publisher = BuildPublisher.get_publisher()

        return publisher.tags(self.build)

    @cached_property
    def pulled(self) -> bool:
        publisher = BuildPublisher.get_publisher()

        return publisher.pulled(self.build)

    @cached_property
    def packages(self) -> list[str] | None:
        publisher = BuildPublisher.get_publisher()

        if not publisher.pulled(self.build):
            return None

        try:
            return [package.cpv for package in publisher.get_packages(self.build)]
        except LookupError:
            return None

    @cached_property
    def packages_built(self) -> list[Package] | None:
        publisher = BuildPublisher.get_publisher()

        try:
            gbp_metadata = publisher.storage.get_metadata(self.build)
        except LookupError as error:
            raise GraphQLError("Packages built unknown") from error

        return gbp_metadata.packages.built

    @cached_property
    def record(self) -> BuildRecord:
        publisher = BuildPublisher.get_publisher()

        if self._record is None:
            self._record = publisher.record(self.build)

        return self._record


class MachineInfoProxy:  # pylint: disable=too-few-public-methods
    """A wrapper around MachineInfo

    We mostly need this to ensure that MachineInfo's Build objects get converted to
    BuildProxy objects.
    """

    def __init__(self, machine_info: MachineInfo):
        self.machine_info = machine_info

    def __getattr__(self, name: str) -> Any:
        if name in {"latest_build", "published_build"}:
            value = getattr(self.machine_info, name)
            return BuildProxy(value) if value else None

        if name == "builds":
            value = getattr(self.machine_info, name)
            return [BuildProxy(i) for i in value]

        return getattr(self.machine_info, name)


@query.field("machines")
def resolve_query_machines(
    _obj: Any, _info: GraphQLResolveInfo
) -> list[MachineInfoProxy]:
    publisher = BuildPublisher.get_publisher()

    return [MachineInfoProxy(machine_info) for machine_info in publisher.machines()]


@query.field("build")
def resolve_query_build(
    _obj: Any, _info: GraphQLResolveInfo, id: str
) -> BuildProxy | None:
    publisher = BuildPublisher.get_publisher()
    build = Build.from_id(id)

    return None if not publisher.records.exists(build) else BuildProxy(build)


@query.field("latest")
def resolve_query_latest(
    _obj: Any, _info: GraphQLResolveInfo, machine: str
) -> BuildProxy | None:
    publisher = BuildPublisher.get_publisher()
    record = publisher.latest_build(machine, completed=True)

    return None if record is None else BuildProxy(record)


@query.field("builds")
def resolve_query_builds(
    _obj: Any, _info: GraphQLResolveInfo, machine: str
) -> list[BuildProxy]:
    publisher = BuildPublisher.get_publisher()

    return [
        BuildProxy(record)
        for record in publisher.records.for_machine(machine)
        if record.completed
    ]


@query.field("diff")
def resolve_query_diff(
    _obj: Any, _info: GraphQLResolveInfo, left: str, right: str
) -> Object | None:
    publisher = BuildPublisher.get_publisher()
    left_build = Build.from_id(left)

    if not publisher.records.exists(left_build):
        raise GraphQLError(f"Build does not exist: {left}")

    right_build = Build.from_id(right)

    if not publisher.records.exists(right_build):
        raise GraphQLError(f"Build does not exist: {right}")

    items = publisher.diff_binpkgs(left_build, right_build)

    return {
        "left": BuildProxy(left_build),
        "right": BuildProxy(right_build),
        "items": [*items],
    }


@query.field("search")
def resolve_query_search(
    _obj: Any, _info: GraphQLResolveInfo, machine: str, field: str, key: str
) -> list[BuildProxy]:
    search_field = {"NOTES": "note", "LOGS": "logs"}[field]
    publisher = BuildPublisher.get_publisher()

    return [BuildProxy(i) for i in publisher.search(machine, search_field, key)]


@query.field("searchNotes")
def resolve_query_searchnotes(
    _obj: Any, _info: GraphQLResolveInfo, machine: str, key: str
) -> list[BuildProxy]:
    publisher = BuildPublisher.get_publisher()

    return [BuildProxy(i) for i in publisher.search(machine, "note", key)]


@query.field("version")
def resolve_query_version(_obj: Any, _info: GraphQLResolveInfo) -> str:
    return get_version()


@query.field("working")
def resolve_query_working(_obj: Any, _info: GraphQLResolveInfo) -> list[BuildProxy]:
    publisher = BuildPublisher.get_publisher()
    build_types = []
    machines = publisher.records.list_machines()

    for machine in machines:
        for record in publisher.records.for_machine(machine):
            if not record.completed:
                build_types.append(BuildProxy(record))

    return build_types


@query.field("resolveBuildTag")
def resolve_query_resolvebuildtag(
    _obj: Any, _info: GraphQLResolveInfo, machine: str, tag: str
) -> BuildProxy | None:
    publisher = BuildPublisher.get_publisher()

    try:
        result = publisher.storage.resolve_tag(f"{machine}{TAG_SYM}{tag}")
    except FileNotFoundError:
        return None

    return BuildProxy(result)


@mutation.field("publish")
def resolve_mutation_publish(
    _obj: Any, _info: GraphQLResolveInfo, id: str
) -> MachineInfo:
    publisher = BuildPublisher.get_publisher()
    build = Build.from_id(id)

    if publisher.pulled(build):
        publisher.publish(build)
    else:
        jobs.from_settings(Settings.from_environ()).publish_build(build.id)

    return MachineInfo(build.machine)


@mutation.field("pull")
def resolve_mutation_pull(
    _obj: Any, _info: GraphQLResolveInfo, *, id: str, note: str | None = None
) -> MachineInfo:
    build = Build.from_id(id)

    jobs.from_settings(Settings.from_environ()).pull_build(build.id, note=note)

    return MachineInfo(build.machine)


@mutation.field("scheduleBuild")
def resolve_mutation_schedule_build(
    _obj: Any, _info: GraphQLResolveInfo, machine: str
) -> str:
    publisher = BuildPublisher.get_publisher()

    return publisher.schedule_build(machine)


@mutation.field("keepBuild")
def resolve_mutation_keepbuild(
    _obj: Any, _info: GraphQLResolveInfo, id: str
) -> BuildProxy | None:
    publisher = BuildPublisher.get_publisher()
    build = Build.from_id(id)

    if not publisher.records.exists(build):
        return None

    record = publisher.record(build).save(publisher.records, keep=True)

    return BuildProxy(record)


@mutation.field("releaseBuild")
def resolve_mutation_releasebuild(
    _obj: Any, _info: GraphQLResolveInfo, id: str
) -> BuildProxy | None:
    publisher = BuildPublisher.get_publisher()
    build = Build.from_id(id)

    if not publisher.records.exists(build):
        return None

    record = publisher.record(build).save(publisher.records, keep=False)

    return BuildProxy(record)


@mutation.field("createNote")
def resolve_mutation_createnote(
    _obj: Any, _info: GraphQLResolveInfo, id: str, note: str | None = None
) -> BuildProxy | None:
    publisher = BuildPublisher.get_publisher()
    build = Build.from_id(id)

    if not publisher.records.exists(build):
        return None

    record = publisher.record(build).save(publisher.records, note=note)

    return BuildProxy(record)


@mutation.field("createBuildTag")
def resolve_mutation_createbuildtag(
    _obj: Any, _info: GraphQLResolveInfo, id: str, tag: str
) -> BuildProxy:
    publisher = BuildPublisher.get_publisher()
    build = Build.from_id(id)

    publisher.tag(build, tag)

    return BuildProxy(build)


@mutation.field("removeBuildTag")
def resolve_mutation_removebuildtag(
    _obj: Any, _info: GraphQLResolveInfo, machine: str, tag: str
) -> MachineInfo:
    publisher = BuildPublisher.get_publisher()

    publisher.untag(machine, tag)

    return MachineInfo(machine)


@mutation.field("createRepo")
@require_localhost
def resolve_mutation_createrepo(
    _obj: Any, _info: GraphQLResolveInfo, name: str, repo: str, branch: str
) -> Error | None:
    jenkins = BuildPublisher.get_publisher().jenkins

    jenkins.make_folder(jenkins.project_root / "repos", parents=True, exist_ok=True)

    try:
        jenkins.create_repo_job(name, repo, branch)
    except (FileExistsError, FileNotFoundError) as error:
        return Error.from_exception(error)

    return None


@mutation.field("createMachine")
@require_localhost
def resolve_mutation_create_machine(
    _obj: Any,
    _info: GraphQLResolveInfo,
    name: str,
    repo: str,
    branch: str,
    ebuildRepos: list[str],
) -> Error | None:
    jenkins = BuildPublisher.get_publisher().jenkins

    jenkins.make_folder(jenkins.project_root, parents=True, exist_ok=True)

    try:
        jenkins.create_machine_job(name, repo, branch, ebuildRepos)
    except (FileExistsError, FileNotFoundError) as error:
        return Error.from_exception(error)

    return None


MERGED_TYPE_DEFS, MERGED_RESOLVERS = load_schema()
schema = make_executable_schema(
    MERGED_TYPE_DEFS, *MERGED_RESOLVERS, snake_case_fallback_resolvers
)
