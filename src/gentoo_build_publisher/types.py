"""Basic Build interface for Gentoo Build Publisher"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum, unique
from typing import Any

from dataclasses_json import dataclass_json

from . import utils


class InvalidBuild(ValueError):
    """Build not in name.number format"""


class Build:
    """A build ID (name.number)"""

    def __init__(self, id_: str):
        self._id = id_

        if not all(parts := id_.partition(".")):
            raise InvalidBuild(self)

        self.name = parts[0]

        try:
            self.number = int(parts[2])
        except ValueError as error:
            raise InvalidBuild(str(error)) from error

    @property
    def id(self):  # pylint: disable=invalid-name
        """Return the string representation of the Build"""
        return self._id

    def __str__(self) -> str:
        return self._id

    def __hash__(self) -> int:
        return hash(self._id)

    def __eq__(self, other: Any) -> bool:
        return type(self) is type(other) and self.id == other.id


class BuildRecord(Build):
    """A Build record from the database"""

    def __init__(
        self,
        id_: str,
        *,
        note: str | None = None,
        logs: str | None = None,
        keep: bool = False,
        submitted: dt.datetime | None = None,
        completed: dt.datetime | None = None,
    ):
        super().__init__(id_)
        self.note = note
        self.logs = logs
        self.keep = keep
        self.submitted = submitted
        self.completed = completed

    def __eq__(self, other: Any) -> bool:
        if type(self) is not type(other):
            return False

        return (
            self.id,
            self.note,
            self.logs,
            self.keep,
            self.submitted,
            self.completed,
        ) == (
            other.id,
            other.note,
            other.logs,
            other.keep,
            other.submitted,
            other.completed,
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}({(self.id)!r})"

    def __hash__(self) -> int:
        return hash(self.id)


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
