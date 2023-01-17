"""DB interface for Gentoo Build Publisher"""
from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable
from typing import Any, Protocol, Type

from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.types import Build, BuildRecord


class RecordDB(Protocol):  # pragma: no cover
    """Repository for BuildRecords"""

    # pylint: disable=unnecessary-ellipsis

    def save(self, build_record: BuildRecord, **fields: Any) -> None:
        """Save changes back to the database"""
        ...

    def get(self, build: Build) -> BuildRecord:
        """Retrieve db record"""
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


class Records:  # pylint: disable=too-few-public-methods
    """Just a wrapper to look like storage and jenkins modules"""

    @staticmethod
    def from_settings(settings: Settings) -> RecordDB:
        """Return instance of the the RecordDB class given in settings"""
        try:
            [backend] = importlib.metadata.entry_points(
                group="gentoo_build_publisher.records", name=settings.RECORDS_BACKEND
            )
        except ValueError:
            raise LookupError(
                f"RECORDS_BACKEND not found: {settings.RECORDS_BACKEND}"
            ) from None

        record_db: Type[RecordDB] = backend.load()

        return record_db()
