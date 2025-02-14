"""Resolvers for the GraphQL Mutation type"""

from typing import Any, TypeAlias, TypedDict

from ariadne import ObjectType, convert_kwargs_to_snake_case
from graphql import GraphQLResolveInfo

from gentoo_build_publisher import publisher, worker
from gentoo_build_publisher.machines import MachineInfo
from gentoo_build_publisher.records import BuildRecord
from gentoo_build_publisher.types import Build, EbuildRepo, MachineJob, Repo
from gentoo_build_publisher.worker import tasks

from .utils import Error, maybe_require_apikey

Mutation = ObjectType("Mutation")

Info: TypeAlias = GraphQLResolveInfo
Object: TypeAlias = dict[str, Any]

# pylint: disable=redefined-builtin
# pylint: disable=missing-function-docstring


class BuildParameterInput(TypedDict):
    """Python analog to the BuildParameter Graphql type"""

    name: str
    value: str


@Mutation.field("pull")
@maybe_require_apikey
def pull(
    _obj: Any,
    _info: Info,
    *,
    id: str,
    note: str | None = None,
    tags: list[str] | None = None,
) -> MachineInfo:
    build = Build.from_id(id)

    worker.run(tasks.pull_build, build.id, note=note, tags=tags)

    return MachineInfo(build.machine)


@Mutation.field("scheduleBuild")
@convert_kwargs_to_snake_case
@maybe_require_apikey
def schedule_build(
    _obj: Any,
    _info: Info,
    machine: str,
    is_repo: bool = False,
    params: list[BuildParameterInput] | None = None,
) -> str | None:
    params = params or []
    job = f"repos/job/{machine}" if is_repo else machine

    return publisher.schedule_build(job, **{p["name"]: p["value"] for p in params})


@Mutation.field("keepBuild")
@maybe_require_apikey
def keepbuild(_obj: Any, _info: Info, id: str) -> BuildRecord | None:
    build = Build.from_id(id)

    if not publisher.repo.build_records.exists(build):
        return None

    return publisher.save(publisher.record(build), keep=True)


@Mutation.field("releaseBuild")
@maybe_require_apikey
def releasebuild(_obj: Any, _info: Info, id: str) -> BuildRecord | None:
    build = Build.from_id(id)

    if not publisher.repo.build_records.exists(build):
        return None

    return publisher.save(publisher.record(build), keep=False)


@Mutation.field("createNote")
@maybe_require_apikey
def createnote(
    _obj: Any, _info: Info, id: str, note: str | None = None
) -> BuildRecord | None:
    build = Build.from_id(id)

    if not publisher.repo.build_records.exists(build):
        return None

    return publisher.save(publisher.record(build), note=note)


@Mutation.field("createBuildTag")
@maybe_require_apikey
def createbuildtag(_obj: Any, _info: Info, id: str, tag: str) -> Build:
    build = Build.from_id(id)

    publisher.tag(build, tag)

    return build


@Mutation.field("removeBuildTag")
@maybe_require_apikey
def removebuildtag(_obj: Any, _info: Info, machine: str, tag: str) -> MachineInfo:
    publisher.untag(machine, tag)

    return MachineInfo(machine)


@Mutation.field("createRepo")
@maybe_require_apikey
def createrepo(
    _obj: Any, _info: Info, name: str, repo: str, branch: str
) -> Error | None:
    jenkins = publisher.jenkins

    jenkins.make_folder(jenkins.project_root / "repos", parents=True, exist_ok=True)

    try:
        jenkins.create_repo_job(EbuildRepo(name=name, url=repo, branch=branch))
    except (FileExistsError, FileNotFoundError) as error:
        return Error.from_exception(error)

    return None


@Mutation.field("createMachine")
@convert_kwargs_to_snake_case
@maybe_require_apikey
def create_machine(
    _obj: Any, _info: Info, name: str, repo: str, branch: str, ebuild_repos: list[str]
) -> Error | None:
    jenkins = publisher.jenkins

    jenkins.make_folder(jenkins.project_root, parents=True, exist_ok=True)

    job = MachineJob(
        name=name, repo=Repo(url=repo, branch=branch), ebuild_repos=ebuild_repos
    )
    try:
        jenkins.create_machine_job(job)
    except (FileExistsError, FileNotFoundError) as error:
        return Error.from_exception(error)

    return None


@Mutation.field("publish")
@maybe_require_apikey
def publish(_obj: Any, _info: Info, id: str) -> MachineInfo:
    build = Build.from_id(id)

    if publisher.pulled(build):
        publisher.publish(build)
    else:
        worker.run(tasks.publish_build, build.id)

    return MachineInfo(build.machine)
