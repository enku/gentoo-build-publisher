"""Common data types for Gentoo Build Publisher"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from typing import Any, Protocol

from gentoo_build_publisher import utils

# Symbol used to designate a build tag
TAG_SYM = "@"


class InvalidBuild(ValueError):
    """Build not in machine.build_id format"""


@dataclass(frozen=True, slots=True)
class Build:
    """A build ID (machine.build_id)"""

    machine: str
    """Machine name for the build"""

    build_id: str
    """Machine "id" for the build.  For Jenkins this an integer sequence"""

    @property
    def id(self) -> str:  # pylint: disable=invalid-name
        """Return the string representation of the Build"""
        return f"{self.machine}.{self.build_id}"

    @classmethod
    def from_id(cls, build_id: str) -> Build:
        """Instantiate Build gienven the build id"""
        machine, build_id = build_id.split(".", 1)

        if not (machine and build_id):
            raise InvalidBuild(build_id)

        return cls(machine, build_id)

    def __str__(self) -> str:
        return self.id

    def __repr__(self) -> str:
        return f"{type(self).__qualname__}({self.id!r})"


@unique
class Content(Enum):
    """Each build (should) contain these contents"""

    REPOS = "repos"
    BINPKGS = "binpkgs"
    ETC_PORTAGE = "etc-portage"
    VAR_LIB_PORTAGE = "var-lib-portage"


@dataclass(frozen=True, slots=True)
class Package:
    """A Gentoo binary package"""

    cpv: str
    """Gentoo CPV (category-package-version)"""

    repo: str
    """The repo (overlay) name where the package came"""

    path: str
    """Path name of the binary package"""

    build_id: int
    """Binary package build id"""

    size: int
    """Size (in bytes) of the files in the package"""

    build_time: int
    """Unix time that the package was built"""

    def cpvb(self) -> str:
        """return cpv + build id"""
        return f"{self.cpv}-{self.build_id}"


class Status(Enum):
    """Change item status (added, changed, removed)"""

    REMOVED = -1
    CHANGED = 0
    ADDED = 1


@dataclass(frozen=True, slots=True)
class Change:
    """A changed item (file or directory)"""

    item: str
    status: Status


@dataclass(frozen=True, slots=True)
class PackageMetadata:
    """data structure for a build's package metadata"""

    total: int
    size: int
    built: list[Package]


@dataclass(frozen=True, slots=True)
class GBPMetadata:
    """data structure combining Jenkins and package metadata

    The manager writes this to each build's binpkg directory as gbp.json.
    """

    build_duration: int
    packages: PackageMetadata
    gbp_hostname: str = utils.get_hostname()
    gbp_version: str = utils.get_version()


class CacheProtocol(Protocol):
    """Something that can cache... like Django's cache"""

    # pylint: disable=missing-docstring
    def get(self, key: str, default: Any = None) -> Any:
        """Return the given key from the cache or `default` if it doesn't exist"""

    def set(self, key: str, value: Any) -> None:
        """Set a value in the cache"""


@dataclass(frozen=True, slots=True, kw_only=True)
class Repo:
    """A (git) repo"""

    url: str
    branch: str


@dataclass(frozen=True, slots=True, kw_only=True)
class EbuildRepo(Repo):
    """An repository for ebuilds (e.g. "gentoo")"""

    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MachineJob:
    """A machine job definition"""

    name: str
    repo: Repo
    ebuild_repos: list[str]
