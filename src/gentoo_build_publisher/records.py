"""DB interface for Gentoo Build Publisher"""
from __future__ import annotations

import datetime as dt
import importlib
from collections.abc import Iterable
from typing import Any, Protocol

from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.types import Build


class RecordNotFound(LookupError):
    """Not found exception for the .get() method"""


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
        built: dt.datetime | None = None,
    ):
        super().__init__(id_)
        self.note = note
        self.logs = logs
        self.keep = keep
        self.submitted = submitted
        self.completed = completed
        self.built = built

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
            self.built,
        ) == (
            other.id,
            other.note,
            other.logs,
            other.keep,
            other.submitted,
            other.completed,
            other.built,
        )

    def __repr__(self) -> str:
        return f"{self.__class__.__qualname__}({(self.id)!r})"

    def __hash__(self) -> int:
        return hash(self.id)


class RecordDB(Protocol):  # pragma: no cover
    """Repository for BuildRecords"""

    def save(self, build_record: BuildRecord, **fields) -> None:
        """Save changes back to the database"""
        ...

    def get(self, build: Build) -> BuildRecord:
        """Retrieve db record"""
        ...

    def query(self, **filters) -> Iterable[BuildRecord]:
        """Query the database and return an iterable of BuildRecord objects

        The order of the builds are by the submitted time, most recent first.

        For example:

            >>> RecordDB.query(name="babette")
        """
        ...

    def for_machine(self, machine: str) -> Iterable[BuildRecord]:
        """Return BuildRecords for the given machine"""
        ...

    def delete(self, build: Build) -> None:
        """Delete this Build from the db"""
        ...

    def exists(self, build: Build) -> bool:
        """Return True iff a record of the build exists in the database"""
        ...

    def list_machines(self) -> list[str]:
        """Return a list of machine names"""
        ...

    def previous(self, build_id: Build, completed: bool = True) -> BuildRecord | None:
        """Return the previous build in the db or None"""
        ...

    def next_build(self, build: Build, completed: bool = True) -> BuildRecord | None:
        """Return the next build in the db or None"""
        ...

    def latest_build(self, name: str, completed: bool = False) -> BuildRecord | None:
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


class Records:  # pylint: disable=too-few-public-methods
    """Just a wrapper to look like storage and jenkins modules"""

    @staticmethod
    def from_settings(_settings: Settings) -> RecordDB:
        """This simply returns the Django model as that's the only implementation"""
        models = importlib.import_module("gentoo_build_publisher.models")

        return models.RecordDB()
