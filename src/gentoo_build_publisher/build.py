"""Basic Build interface for Gentoo Build Publisher"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique

from dataclasses_json import dataclass_json

from gentoo_build_publisher import utils


class InvalidBuildID(ValueError):
    """BuildID not in name.number format"""


class BuildID(str):
    """A build ID (name.number)"""

    def __init__(self, _):
        super().__init__()

        if not all(parts := self.partition(".")):
            raise InvalidBuildID(self)

        self.name = parts[0]

        try:
            self.number = int(parts[2])
        except ValueError as error:
            raise InvalidBuildID(str(error)) from error


@unique
class Content(Enum):
    """Each build (should) contain these contents"""

    REPOS = "repos"
    BINPKGS = "binpkgs"
    ETC_PORTAGE = "etc-portage"
    VAR_LIB_PORTAGE = "var-lib-portage"


@dataclass
class Package:
    """A Gentoo binary package"""

    cpv: str
    repo: str
    path: str
    build_id: int
    size: int
    build_time: int

    def cpvb(self) -> str:
        """return cpv + build id"""
        return f"{self.cpv}-{self.build_id}"


class Status(Enum):
    """Change item status (added, changed, removed)"""

    REMOVED = -1
    CHANGED = 0
    ADDED = 1


@dataclass(frozen=True)
class Change:
    """A changed item (file or directory)"""

    item: str
    status: Status


@dataclass_json
@dataclass
class PackageMetadata:
    """data structure for a build's package metadata"""

    total: int
    size: int
    built: list[Package]


@dataclass_json
@dataclass
class GBPMetadata:
    """data structure combining Jenkins and package metadata

    The manager writes this to each build's binpkg directory as gbp.json.
    """

    build_duration: int
    packages: PackageMetadata
    gbp_hostname: str = utils.get_hostname()
    gbp_version: str = utils.get_version()
