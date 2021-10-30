"""Basic Build interface for Gentoo Build Publisher"""
import datetime as dt
from dataclasses import dataclass
from enum import Enum, unique


@dataclass
class Build:
    """A Representation of a Jenkins build artifact"""

    name: str
    number: int

    def __str__(self):
        return f"{self.name}.{self.number}"


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
    build_time: dt.datetime

    def cpvb(self) -> str:
        """return cpv + build id"""
        return f"{self.cpv}-{self.build_id}"


class Status(Enum):
    """Change item status (added, changed, removed)"""

    REMOVED = -1
    CHANGED = 0
    ADDED = 1

    def is_a_build(self):
        """Return true if this is a "build" change"""
        return self is not Status.REMOVED


@dataclass(frozen=True)
class Change:
    """A changed item (file or directory)"""

    item: str
    status: Status
