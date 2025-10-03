"""helpers for writing tests"""

# pylint: disable=missing-docstring
from typing import Any
from unittest import mock

from gbp_testkit.factories import ArtifactFactory, BuildFactory, package_factory
from gentoo_build_publisher.types import Build

PACKAGE_LINES: list[str] = [
    "BDEPEND: >=sys-devel/gettext-0.19.8 app-arch/xz-utils >=dev-util/meson-0.62.2",
    "BUILD_ID: 3",
    "BUILD_TIME: 1666772558",
    "CPV: x11-themes/gnome-backgrounds-43-r1",
    "DEFINED_PHASES: compile configure install test",
    "EAPI: 8",
    "KEYWORDS: ~amd64 ~arm ~arm64 ~ppc ~ppc64 ~x86",
    "LICENSE: CC-BY-SA-2.0 CC-BY-SA-3.0 CC-BY-2.0 CC-BY-4.0",
    "MD5: add4d9febc08ba733c03e27a63ec2d1b",
    "PATH: x11-themes/gnome-backgrounds/gnome-backgrounds-43-r1-4.gpkg.tar",
    "RDEPEND: gui-libs/gdk-pixbuf-loader-webp",
    "SHA1: 6f1008246685b0a379fa286add1d782bf79a7d9d",
    "SIZE: 32530181",
    "USE: abi_x86_64 amd64 elibc_glibc kernel_linux userland_GNU",
    "MTIME: 1666772566",
    "REPO: gentoo",
]


def make_entry_point(name: str, loaded_value: Any) -> mock.Mock:
    ep = mock.Mock()
    ep.name = name
    ep.load.return_value = loaded_value
    return ep


def create_builds_and_packages(
    machine: str, number_of_builds: int, pkgs_per_build: int, builder: ArtifactFactory
) -> list[Build]:
    builds: list[Build] = BuildFactory.build_batch(number_of_builds, machine=machine)
    pf = package_factory()

    for build in builds:
        for _ in range(pkgs_per_build):
            package = next(pf)
            builder.build(build, package)

    return builds
