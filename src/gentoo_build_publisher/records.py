"""DB interface for Gentoo Build Publisher"""
from __future__ import annotations

import importlib
from typing import Iterator, Protocol

from gentoo_build_publisher.build import Build, BuildRecord
from gentoo_build_publisher.settings import Settings


class RecordNotFound(LookupError):
    """Not found exception for the .get() method"""


class RecordDB(Protocol):  # pragma: no cover
    """Repository for BuildRecords"""

    def save(self, build_record: BuildRecord, **fields) -> None:
        """Save changes back to the database"""
        ...

    def get(self, build: Build) -> BuildRecord:
        """Retrieve db record"""
        ...

    def query(self, **filters) -> Iterator[BuildRecord]:
        """Query the database and return an iterable of BuildRecord objects

        The order of the builds are by the submitted time, most recent first.

        For example:

            >>> RecordDB.query(name="babette")
        """
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

    def previous_build(
        self, build_id: Build, completed: bool = True
    ) -> BuildRecord | None:
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

    def search_notes(self, machine: str, key: str) -> Iterator[BuildRecord]:
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
