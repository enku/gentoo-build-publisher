"""GraphQL resolvers for Gentoo Build Publisher"""
# Most of the functions are resolvers and need no explanation
# pylint: disable=missing-function-docstring

# "id" is used throughout. It's idiomatic GraphQL
# pylint: disable=redefined-builtin,invalid-name
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from functools import cached_property, wraps
from importlib import resources
from typing import Any, Callable, Optional

from ariadne import (
    EnumType,
    ObjectType,
    gql,
    make_executable_schema,
    snake_case_fallback_resolvers,
)
from ariadne_django.scalars import datetime_scalar
from graphql import GraphQLError, GraphQLResolveInfo

from gentoo_build_publisher.publisher import MachineInfo, get_publisher
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.tasks import publish_build, pull_build
from gentoo_build_publisher.types import TAG_SYM, Build, Package, Status
from gentoo_build_publisher.utils import get_version

LOCALHOST = "127.0.0.1", "::1", "localhost"

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

        if not client_ip in LOCALHOST:
            raise GraphQLError(f"Unauthorized to resolve {info.path.key}")
        return fn(args[0], info, *args[2:], **kwargs)

    return wrapper


@dataclass
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
        publisher = get_publisher()

        return publisher.published(self.build)

    @cached_property
    def tags(self) -> list[str]:
        publisher = get_publisher()

        return publisher.tags(self.build)

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


class MachineInfoProxy:  # pylint: disable=too-few-public-methods
    """A wrapper around MachineInfo

    We mostly need this to ensure that MachineInfo's Build objects get converted to
    BuildProxy objects.
    """

    def __init__(self, machine_info: MachineInfo):
        self.machine_info = machine_info

    def __getattr__(self, name: str) -> Any:
        if name in ["latest_build", "published_build"]:
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
    publisher = get_publisher()

    return [MachineInfoProxy(machine_info) for machine_info in publisher.machines()]


@query.field("build")
def resolve_query_build(
    _obj: Any, _info: GraphQLResolveInfo, id: str
) -> Optional[BuildProxy]:
    publisher = get_publisher()
    build = Build(id)

    return None if not publisher.records.exists(build) else BuildProxy(build)


@query.field("latest")
def resolve_query_latest(
    _obj: Any, _info: GraphQLResolveInfo, machine: str
) -> Optional[BuildProxy]:
    publisher = get_publisher()
    record = publisher.latest_build(machine, completed=True)

    return None if record is None else BuildProxy(record)


@query.field("builds")
def resolve_query_builds(
    _obj: Any, _info: GraphQLResolveInfo, machine: str
) -> list[BuildProxy]:
    publisher = get_publisher()

    return [
        BuildProxy(record)
        for record in publisher.records.for_machine(machine)
        if record.completed
    ]


@query.field("diff")
def resolve_query_diff(
    _obj: Any, _info: GraphQLResolveInfo, left: str, right: str
) -> Optional[Object]:
    publisher = get_publisher()
    left_build = Build(left)

    if not publisher.records.exists(left_build):
        raise GraphQLError(f"Build does not exist: {left}")

    right_build = Build(right)

    if not publisher.records.exists(right_build):
        raise GraphQLError(f"Build does not exist: {right}")

    items = publisher.diff_binpkgs(left_build, right_build)

    return {
        "left": BuildProxy(left_build),
        "right": BuildProxy(right_build),
        "items": [*items],
    }


@query.field("searchNotes")
def resolve_query_searchnotes(
    _obj: Any, _info: GraphQLResolveInfo, machine: str, key: str
) -> list[BuildProxy]:
    publisher = get_publisher()

    return [BuildProxy(i) for i in publisher.search_notes(machine, key)]


@query.field("version")
def resolve_query_version(_obj: Any, _info: GraphQLResolveInfo) -> str:
    return get_version()


@query.field("working")
def resolve_query_working(_obj: Any, _info: GraphQLResolveInfo) -> list[BuildProxy]:
    publisher = get_publisher()
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
) -> Optional[BuildProxy]:
    publisher = get_publisher()

    try:
        result = publisher.storage.resolve_tag(f"{machine}{TAG_SYM}{tag}")
    except FileNotFoundError:
        return None

    return BuildProxy(result)


@mutation.field("publish")
def resolve_mutation_publish(
    _obj: Any, _info: GraphQLResolveInfo, id: str
) -> MachineInfo:
    publisher = get_publisher()
    build = Build(id)

    if publisher.pulled(build):
        publisher.publish(build)
    else:
        publish_build.delay(build.id)

    return MachineInfo(build.machine)


@mutation.field("pull")
def resolve_mutation_pull(_obj: Any, _info: GraphQLResolveInfo, id: str) -> MachineInfo:
    build = Build(id)

    pull_build.delay(id)

    return MachineInfo(build.machine)


@mutation.field("scheduleBuild")
def resolve_mutation_schedule_build(
    _obj: Any, _info: GraphQLResolveInfo, machine: str
) -> str:
    publisher = get_publisher()

    return publisher.schedule_build(machine)


@mutation.field("keepBuild")
def resolve_mutation_keepbuild(
    _obj: Any, _info: GraphQLResolveInfo, id: str
) -> Optional[BuildProxy]:
    publisher = get_publisher()
    build = Build(id)

    if not publisher.records.exists(build):
        return None

    record = publisher.record(build)
    publisher.records.save(record, keep=True)

    return BuildProxy(record)


@mutation.field("releaseBuild")
def resolve_mutation_releasebuild(
    _obj: Any, _info: GraphQLResolveInfo, id: str
) -> Optional[BuildProxy]:
    publisher = get_publisher()
    build = Build(id)

    if not publisher.records.exists(build):
        return None

    record = publisher.record(build)
    publisher.records.save(record, keep=False)

    return BuildProxy(record)


@mutation.field("createNote")
def resolve_mutation_createnote(
    _obj: Any, _info: GraphQLResolveInfo, id: str, note: Optional[str] = None
) -> Optional[BuildProxy]:
    publisher = get_publisher()
    build = Build(id)

    if not publisher.records.exists(build):
        return None

    record = publisher.record(build)
    publisher.records.save(record, note=note)

    return BuildProxy(record)


@mutation.field("createBuildTag")
def resolve_mutation_createbuildtag(
    _obj: Any, _info: GraphQLResolveInfo, id: str, tag: str
) -> BuildProxy:
    publisher = get_publisher()
    build = Build(id)

    publisher.tag(build, tag)

    return BuildProxy(build)


@mutation.field("removeBuildTag")
def resolve_mutation_removebuildtag(
    _obj: Any, _info: GraphQLResolveInfo, machine: str, tag: str
) -> MachineInfo:
    publisher = get_publisher()

    publisher.untag(machine, tag)

    return MachineInfo(machine)


@mutation.field("createRepo")
@require_localhost
def resolve_mutation_createrepo(
    _obj: Any, _info: GraphQLResolveInfo, name: str, repo: str, branch: str
) -> Optional[Error]:
    jenkins = get_publisher().jenkins

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
    ebuild_repos: list[str],
) -> Optional[Error]:
    jenkins = get_publisher().jenkins

    jenkins.make_folder(jenkins.project_root, parents=True, exist_ok=True)

    try:
        jenkins.create_machine_job(name, repo, branch, ebuild_repos)
    except (FileExistsError, FileNotFoundError) as error:
        return Error.from_exception(error)

    return None


schema = make_executable_schema(type_defs, resolvers, snake_case_fallback_resolvers)
