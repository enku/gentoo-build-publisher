"""Resolvers for the GraphQL Build type"""

# pylint: disable=missing-function-docstring

import datetime as dt

from ariadne import ObjectType, convert_kwargs_to_snake_case
from django.urls import reverse
from graphql import GraphQLResolveInfo

from gentoo_build_publisher import publisher
from gentoo_build_publisher.types import Build, Package
from gentoo_build_publisher.utils import string

type Info = GraphQLResolveInfo

BUILD = ObjectType("Build")
PACKAGE = ObjectType("Package")


@BUILD.field("built")
def _(build: Build, _info: Info) -> dt.datetime | None:
    return publisher.record(build).built


@BUILD.field("completed")
def _(build: Build, _info: Info) -> dt.datetime | None:
    return publisher.record(build).completed


@BUILD.field("keep")
def _(build: Build, _info: Info) -> bool:
    return publisher.record(build).keep


@BUILD.field("logs")
def _(build: Build, _info: Info) -> str | None:
    return publisher.record(build).logs


@BUILD.field("notes")
def _(build: Build, _info: Info) -> str | None:
    return publisher.record(build).note


@BUILD.field("packages")
@convert_kwargs_to_snake_case
def _(build: Build, _info: Info, build_id: bool = False) -> list[str] | None:
    if not publisher.pulled(build):
        return None

    try:
        packages = publisher.get_packages(build)
    except LookupError:
        return None

    if build_id:
        return [package.cpvb() for package in packages]
    return [package.cpv for package in packages]


@BUILD.field("packagesBuilt")
def _(build: Build, _info: Info) -> list[Package] | None:
    gbp_metadata = publisher.build_metadata(build)

    return gbp_metadata.packages.built


@BUILD.field("published")
def _(build: Build, _info: Info) -> bool:
    return publisher.published(build)


@BUILD.field("pulled")
def _(build: Build, _info: Info) -> bool:
    return publisher.pulled(build)


@BUILD.field("submitted")
def _(build: Build, _info: Info) -> dt.datetime:
    return publisher.record(build).submitted or dt.datetime.now(tz=dt.UTC)


@BUILD.field("tags")
def _(build: Build, _info: Info) -> list[str]:
    return publisher.tags(build)


@BUILD.field("packageDetail")
def _(build: Build, _info: Info) -> list[Package]:
    build_record = publisher.record(build)

    return publisher.get_packages(build_record)


@BUILD.field("profile")
def _(build: Build, _info: Info) -> str | None:
    try:
        return publisher.portage_profile(build)
    except FileNotFoundError:
        return None


@PACKAGE.field("url")
def _(package: Package, _info: Info) -> str:
    # circular-import workaround
    # pylint: disable=import-outside-toplevel
    c, p, v = string.split_pkg(package.cpv)
    build = package.build
    view_args = {
        "machine": build.machine,
        "build_id": build.build_id,
        "c": c,
        "p": p,
        "pv": f"{p}-{v}",
        "b": package.build_id,
    }

    return reverse("gbp-binpkg", kwargs=view_args)
