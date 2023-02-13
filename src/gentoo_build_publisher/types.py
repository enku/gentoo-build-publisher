"""Basic Build interface for Gentoo Build Publisher"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum, unique
from typing import Any, Iterable, NamedTuple, Protocol

from dataclasses_json import dataclass_json

from gentoo_build_publisher import utils

# Symbol used to designate a build tag
TAG_SYM = "@"


class InvalidBuild(ValueError):
    """Build not in machine.build_id format"""


class RecordNotFound(LookupError):
    """Not found exception for the .get() method"""


class Build(NamedTuple):
    """A build ID (machine.build_id)"""

    machine: str
    """Machine name for the build"""

    build_id: str
    """Machine "id" for the build.  For Jenkins this an integer sequence"""

    @property
    def id(self) -> str:  # pylint: disable=invalid-name
        """Return the string representation of the Build"""
        return ".".join(self)

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


class BuildRecord(NamedTuple):
    """A Build record from the database"""

    machine: str
    """Machine name for the build"""

    build_id: str
    """Machine "id" for the build.  For Jenkins this an integer sequence"""

    note: str | None = None
    """Optional user-created build note"""

    logs: str | None = None
    """(Jenkins) build log"""

    keep: bool = False
    """Whether nor not the purger should skip this build record"""

    submitted: dt.datetime | None = None
    """Timestamp the build was submitted to gbp"""

    completed: dt.datetime | None = None
    """Timestamp when the build was completely pulled by gbp"""

    built: dt.datetime | None = None
    """(Jenkins) timestamp when the build started"""

    def __str__(self) -> str:
        return self.id

    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}({(self.id)!r})"

    @property
    def id(self) -> str:  # pylint: disable=invalid-name
        """Return the string representation of the Build"""
        return f"{self.machine}.{self.build_id}"

    def purge_key(self) -> dt.datetime:
        """Purge key for build records.  Purge on submitted date"""
        submitted = self.submitted or dt.datetime.fromtimestamp(0)

        return submitted.replace(tzinfo=None)

    def save(self, record_db: RecordDB, **fields: Any) -> BuildRecord:
        """Save changes to record_db. Return new record"""
        return record_db.save(self, **fields)


class RecordDB(Protocol):  # pragma: no cover
    """Repository for BuildRecords"""

    # pylint: disable=unnecessary-ellipsis

    def save(self, build_record: BuildRecord, **fields: Any) -> BuildRecord:
        """Save changes back to the database"""
        ...

    def get(self, build: BuildLike) -> BuildRecord:
        """Retrieve db record"""
        ...

    def for_machine(self, machine: str) -> Iterable[BuildRecord]:
        """Return BuildRecords for the given machine"""
        ...

    def delete(self, build: BuildLike) -> None:
        """Delete this Build from the db"""
        ...

    def exists(self, build: Build) -> bool:
        """Return True iff a record of the build exists in the database"""
        ...

    def list_machines(self) -> list[str]:
        """Return a list of machine names"""
        ...

    def previous(
        self, build_id: BuildRecord, completed: bool = True
    ) -> BuildRecord | None:
        """Return the previous build in the db or None"""
        ...

    def next(self, build: BuildRecord, completed: bool = True) -> BuildRecord | None:
        """Return the next build in the db or None"""
        ...

    def latest(self, name: str, completed: bool = False) -> BuildRecord | None:
        """Return the latest build for the given machine name.

        If `completed` is `True`, only consider completed builds.
        If no builds exist for the given machine name, return None.
        """
        ...

    def search_notes(self, machine: str, key: str) -> Iterable[BuildRecord]:
        """search notes for given machine"""
        ...

    def count(self, name: str | None = None) -> int:
        """Return the total number of builds

        If `name` is given, return the total number of builds for the given machine
        """
        ...


@unique
class Content(Enum):
    """Each build (should) contain these contents"""

    REPOS = "repos"
    BINPKGS = "binpkgs"
    ETC_PORTAGE = "etc-portage"
    VAR_LIB_PORTAGE = "var-lib-portage"


@dataclass(frozen=True)
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


class CacheProtocol(Protocol):  # pragma: no cover
    """Something that can cache... like Django's cache"""

    # pylint: disable=missing-docstring
    def get(self, key: str, default: Any = None) -> Any:
        ...

    def set(self, key: str, value: Any) -> None:
        ...


class BuildLike(Protocol):
    """That which has a machine name and build_id"""

    @property
    def machine(self) -> str:
        """Machine name for the build"""

    @property
    def build_id(self) -> str:
        """Machine "id" for the build.  For Jenkins this an integer sequence"""

    @property
    def id(self) -> str:  # pylint: disable=invalid-name
        """{build.machine}.{build.build_id}"""

    def __hash__(self) -> int:
        ...
