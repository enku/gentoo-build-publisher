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
def built(build: Build, _info: Info) -> dt.datetime | None:
    return publisher.record(build).built


@BUILD.field("completed")
def completed(build: Build, _info: Info) -> dt.datetime | None:
    return publisher.record(build).completed


@BUILD.field("keep")
def keep(build: Build, _info: Info) -> bool:
    return publisher.record(build).keep


@BUILD.field("logs")
def logs(build: Build, _info: Info) -> str | None:
    return publisher.record(build).logs


@BUILD.field("notes")
def notes(build: Build, _info: Info) -> str | None:
    return publisher.record(build).note


@BUILD.field("packages")
@convert_kwargs_to_snake_case
def packages(build: Build, _info: Info, build_id: bool = False) -> list[str] | None:
    if not publisher.pulled(build):
        return None

    try:
        packages_ = publisher.get_packages(build)
    except LookupError:
        return None

    if build_id:
        return [package.cpvb() for package in packages_]
    return [package.cpv for package in packages_]


@BUILD.field("packagesBuilt")
def packages_built(build: Build, _info: Info) -> list[Package] | None:
    gbp_metadata = publisher.build_metadata(build)

    return gbp_metadata.packages.built


@BUILD.field("published")
def published(build: Build, _info: Info) -> bool:
    return publisher.published(build)


@BUILD.field("pulled")
def pulled(build: Build, _info: Info) -> bool:
    return publisher.pulled(build)


@BUILD.field("submitted")
def submitted(build: Build, _info: Info) -> dt.datetime:
    return publisher.record(build).submitted or dt.datetime.now(tz=dt.UTC)


@BUILD.field("tags")
def tags(build: Build, _info: Info) -> list[str]:
    return publisher.tags(build)


@BUILD.field("packageDetail")
def package_detail(build: Build, _info: Info) -> list[Package]:
    build_record = publisher.record(build)

    return publisher.get_packages(build_record)


@BUILD.field("profile")
def profile(build: Build, _info: Info) -> str | None:
    try:
        return publisher.portage_profile(build)
    except FileNotFoundError:
        return None


@PACKAGE.field("url")
def url(package: Package, _info: Info) -> str:
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
