"""Resolvers for the GraphQL Build type"""

import datetime as dt
from typing import TypeAlias

from ariadne import ObjectType
from graphql import GraphQLError, GraphQLResolveInfo

from gentoo_build_publisher import publisher
from gentoo_build_publisher.types import Build, Package

BuildType = ObjectType("Build")
Info: TypeAlias = GraphQLResolveInfo

# pylint: disable=missing-function-docstring


@BuildType.field("built")
def built(build: Build, _info: Info) -> dt.datetime | None:
    return publisher.record(build).built


@BuildType.field("completed")
def completed(build: Build, _info: Info) -> dt.datetime | None:
    return publisher.record(build).completed


@BuildType.field("keep")
def keep(build: Build, _info: Info) -> bool:
    return publisher.record(build).keep


@BuildType.field("logs")
def logs(build: Build, _info: Info) -> str | None:
    return publisher.record(build).logs


@BuildType.field("notes")
def notes(build: Build, _info: Info) -> str | None:
    return publisher.record(build).note


@BuildType.field("packages")
def packages(build: Build, _info: Info) -> list[str] | None:
    if not publisher.pulled(build):
        return None

    try:
        _packages = publisher.get_packages(build)
    except LookupError:
        return None

    return [package.cpv for package in _packages]


@BuildType.field("packagesBuilt")
def packages_built(build: Build, _info: Info) -> list[Package] | None:
    try:
        gbp_metadata = publisher.storage.get_metadata(build)
    except LookupError as error:
        raise GraphQLError("Packages built unknown") from error

    return gbp_metadata.packages.built


@BuildType.field("published")
def published(build: Build, _info: Info) -> bool:
    return publisher.published(build)


@BuildType.field("pulled")
def pulled(build: Build, _info: Info) -> bool:
    return publisher.pulled(build)


@BuildType.field("submitted")
def submitted(build: Build, _info: Info) -> dt.datetime:
    return publisher.record(build).submitted or dt.datetime.now(tz=dt.UTC)


@BuildType.field("tags")
def tags(build: Build, _info: Info) -> list[str]:
    return publisher.tags(build)
