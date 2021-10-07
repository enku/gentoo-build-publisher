"""Basic Build interface for Gentoo Build Publisher"""
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
