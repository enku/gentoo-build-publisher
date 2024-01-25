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
from functools import wraps
from importlib import resources
from typing import Any, TypeAlias, TypedDict

from ariadne import (
    EnumType,
    ObjectType,
    gql,
    make_executable_schema,
    snake_case_fallback_resolvers,
)
from ariadne_django.scalars import datetime_scalar
from graphql import GraphQLError, GraphQLResolveInfo

from gentoo_build_publisher import publisher
from gentoo_build_publisher.common import (
    TAG_SYM,
    Build,
    ChangeState,
    EbuildRepo,
    MachineJob,
    Package,
    Repo,
)
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.utils import get_version
from gentoo_build_publisher.worker import Worker, tasks

LOCALHOST = "127.0.0.1", "::1", "localhost"
SCHEMA_GROUP = "gentoo_build_publisher.graphql_schema"

Info: TypeAlias = GraphQLResolveInfo
Object: TypeAlias = dict[str, Any]
type_defs = gql(resources.read_text("gentoo_build_publisher", "schema.graphql"))
resolvers = [
    EnumType("ChangeStateEnum", ChangeState),
    datetime_scalar,
    build_type := ObjectType("Build"),
    machine_summary := ObjectType("MachineSummary"),
    mutation := ObjectType("Mutation"),
    query := ObjectType("Query"),
]


Resolver = Callable[..., Any]


class BuildParameterInput(TypedDict):
    """Python analog to the BuildParameter Graphql type"""

    name: str
    value: str


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
        info: Info = args[1]
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


@build_type.field("built")
def resolve_build_type_built(build: Build, _info: Info) -> dt.datetime | None:
    return publisher.record(build).built


@build_type.field("completed")
def resolve_build_type_completed(build: Build, _info: Info) -> dt.datetime | None:
    record = publisher.record(build)

    return record.completed


@build_type.field("keep")
def resolve_build_type_keep(build: Build, _info: Info) -> bool:
    return publisher.record(build).keep


@build_type.field("logs")
def resolve_build_type_logs(build: Build, _info: Info) -> str | None:
    return publisher.record(build).logs


@build_type.field("notes")
def resolve_build_type_notes(build: Build, _info: Info) -> str | None:
    return publisher.record(build).note


@build_type.field("packages")
def resolve_build_type_packages(build: Build, _info: Info) -> list[str] | None:
    if not publisher.pulled(build):
        return None

    try:
        packages = publisher.get_packages(build)
    except LookupError:
        return None

    return [package.cpv for package in packages]


@build_type.field("packagesBuilt")
def resolve_build_type_packages_built(
    build: Build, _info: Info
) -> list[Package] | None:
    try:
        gbp_metadata = publisher.storage.get_metadata(build)
    except LookupError as error:
        raise GraphQLError("Packages built unknown") from error

    return gbp_metadata.packages.built


@build_type.field("published")
def resolve_build_type_published(build: Build, _info: Info) -> bool:
    return publisher.published(build)


@build_type.field("pulled")
def resolve_build_type_pulled(build: Build, _info: Info) -> bool:
    return publisher.pulled(build)


@build_type.field("submitted")
def resolve_build_type_submitted(build: Build, _info: Info) -> dt.datetime:
    record = publisher.record(build)

    return record.submitted or dt.datetime.now(tz=dt.UTC)


@build_type.field("tags")
def resolve_build_type_tags(build: Build, _info: Info) -> list[str]:
    return publisher.tags(build)


@machine_summary.field("buildCount")
def resolve_machine_summary_build_count(
    machine_info: publisher.MachineInfo, _info: Info
) -> int:
    return machine_info.build_count


@machine_summary.field("latestBuild")
def resolve_machine_summary_latest_build(
    machine_info: publisher.MachineInfo, _info: Info
) -> Build | None:
    return machine_info.latest_build


@machine_summary.field("publishedBuild")
def resolve_machine_summary_published_build(
    machine_info: publisher.MachineInfo, _info: Info
) -> Build | None:
    return machine_info.published_build


@query.field("machines")
def resolve_query_machines(_obj: Any, _info: Info) -> list[publisher.MachineInfo]:
    return publisher.machines()


@query.field("build")
def resolve_query_build(_obj: Any, _info: Info, id: str) -> Build | None:
    build = Build.from_id(id)

    return None if not publisher.records.exists(build) else build


@query.field("latest")
def resolve_query_latest(_obj: Any, _info: Info, machine: str) -> BuildRecord | None:
    record = publisher.latest_build(machine, completed=True)

    return record


@query.field("builds")
def resolve_query_builds(_obj: Any, _info: Info, machine: str) -> list[BuildRecord]:
    return [
        record for record in publisher.records.for_machine(machine) if record.completed
    ]


@query.field("diff")
def resolve_query_diff(_obj: Any, _info: Info, left: str, right: str) -> Object | None:
    left_build = Build.from_id(left)

    if not publisher.records.exists(left_build):
        raise GraphQLError(f"Build does not exist: {left}")

    right_build = Build.from_id(right)

    if not publisher.records.exists(right_build):
        raise GraphQLError(f"Build does not exist: {right}")

    items = publisher.diff_binpkgs(left_build, right_build)

    return {"left": left_build, "right": right_build, "items": [*items]}


@query.field("search")
def resolve_query_search(
    _obj: Any, _info: Info, machine: str, field: str, key: str
) -> list[BuildRecord]:
    search_field = {"NOTES": "note", "LOGS": "logs"}[field]

    return publisher.search(machine, search_field, key)


@query.field("searchNotes")
def resolve_query_searchnotes(
    _obj: Any, _info: Info, machine: str, key: str
) -> list[BuildRecord]:
    return publisher.search(machine, "note", key)


@query.field("version")
def resolve_query_version(_obj: Any, _info: Info) -> str:
    return get_version()


@query.field("working")
def resolve_query_working(_obj: Any, _info: Info) -> list[BuildRecord]:
    return [
        record
        for machine in publisher.records.list_machines()
        for record in publisher.records.for_machine(machine)
        if not record.completed
    ]


@query.field("resolveBuildTag")
def resolve_query_resolvebuildtag(
    _obj: Any, _info: Info, machine: str, tag: str
) -> Build | None:
    try:
        result = publisher.storage.resolve_tag(f"{machine}{TAG_SYM}{tag}")
    except FileNotFoundError:
        return None

    return result


@mutation.field("publish")
def resolve_mutation_publish(_obj: Any, _info: Info, id: str) -> publisher.MachineInfo:
    build = Build.from_id(id)

    if publisher.pulled(build):
        publisher.publish(build)
    else:
        Worker(Settings.from_environ()).run(tasks.publish_build, build.id)

    return publisher.MachineInfo(build.machine)


@mutation.field("pull")
def resolve_mutation_pull(
    _obj: Any,
    _info: Info,
    *,
    id: str,
    note: str | None = None,
    tags: list[str] | None = None,
) -> publisher.MachineInfo:
    build = Build.from_id(id)

    Worker(Settings.from_environ()).run(
        tasks.pull_build, build.id, note=note, tags=tags
    )

    return publisher.MachineInfo(build.machine)


@mutation.field("scheduleBuild")
def resolve_mutation_schedule_build(
    _obj: Any,
    _info: Info,
    machine: str,
    params: list[BuildParameterInput] | None = None,
) -> str | None:
    params = params or []

    return publisher.schedule_build(machine, **{p["name"]: p["value"] for p in params})


@mutation.field("keepBuild")
def resolve_mutation_keepbuild(_obj: Any, _info: Info, id: str) -> BuildRecord | None:
    build = Build.from_id(id)

    if not publisher.records.exists(build):
        return None

    return publisher.record(build).save(publisher.records, keep=True)


@mutation.field("releaseBuild")
def resolve_mutation_releasebuild(
    _obj: Any, _info: Info, id: str
) -> BuildRecord | None:
    build = Build.from_id(id)

    if not publisher.records.exists(build):
        return None

    return publisher.record(build).save(publisher.records, keep=False)


@mutation.field("createNote")
def resolve_mutation_createnote(
    _obj: Any, _info: Info, id: str, note: str | None = None
) -> BuildRecord | None:
    build = Build.from_id(id)

    if not publisher.records.exists(build):
        return None

    return publisher.record(build).save(publisher.records, note=note)


@mutation.field("createBuildTag")
def resolve_mutation_createbuildtag(_obj: Any, _info: Info, id: str, tag: str) -> Build:
    build = Build.from_id(id)

    publisher.tag(build, tag)

    return build


@mutation.field("removeBuildTag")
def resolve_mutation_removebuildtag(
    _obj: Any, _info: Info, machine: str, tag: str
) -> publisher.MachineInfo:
    publisher.untag(machine, tag)

    return publisher.MachineInfo(machine)


@mutation.field("createRepo")
@require_localhost
def resolve_mutation_createrepo(
    _obj: Any, _info: Info, name: str, repo: str, branch: str
) -> Error | None:
    jenkins = publisher.jenkins

    jenkins.make_folder(jenkins.project_root / "repos", parents=True, exist_ok=True)

    try:
        jenkins.create_repo_job(EbuildRepo(name=name, url=repo, branch=branch))
    except (FileExistsError, FileNotFoundError) as error:
        return Error.from_exception(error)

    return None


@mutation.field("createMachine")
@require_localhost
def resolve_mutation_create_machine(
    _obj: Any,
    _info: Info,
    name: str,
    repo: str,
    branch: str,
    ebuildRepos: list[str],
) -> Error | None:
    jenkins = publisher.jenkins

    jenkins.make_folder(jenkins.project_root, parents=True, exist_ok=True)

    job = MachineJob(
        name=name, repo=Repo(url=repo, branch=branch), ebuild_repos=ebuildRepos
    )
    try:
        jenkins.create_machine_job(job)
    except (FileExistsError, FileNotFoundError) as error:
        return Error.from_exception(error)

    return None


MERGED_TYPE_DEFS, MERGED_RESOLVERS = load_schema()
schema = make_executable_schema(
    MERGED_TYPE_DEFS, *MERGED_RESOLVERS, snake_case_fallback_resolvers
)
