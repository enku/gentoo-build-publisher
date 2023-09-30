"""DB interface for Gentoo Build Publisher"""
from __future__ import annotations

import datetime as dt
import importlib.metadata
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol, Type

from gentoo_build_publisher.common import Build
from gentoo_build_publisher.settings import Settings


class RecordNotFound(LookupError):
    """Not found exception for the .get() method"""


@dataclass(frozen=True)
class BuildRecord(Build):
    """A Build record from the database"""

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

    def __post_init__(self) -> None:
        super().__init__(self.machine, self.build_id)

    def __str__(self) -> str:
        return self.id

    def purge_key(self) -> dt.datetime:
        """Purge key for build records.  Purge on submitted date"""
        submitted = self.submitted or dt.datetime.fromtimestamp(0)

        return submitted.replace(tzinfo=None)

    def save(self, record_db: RecordDB, **fields: Any) -> BuildRecord:
        """Save changes to record_db. Return new record"""
        return record_db.save(self, **fields)


class RecordDB(Protocol):
    """Repository for BuildRecords"""

    def save(self, build_record: BuildRecord, **fields: Any) -> BuildRecord:
        """Save changes back to the database"""

    def get(self, build: Build) -> BuildRecord:
        """Retrieve db record"""

    def for_machine(self, machine: str) -> Iterable[BuildRecord]:
        """Return BuildRecords for the given machine"""

    def delete(self, build: Build) -> None:
        """Delete this Build from the db"""

    def exists(self, build: Build) -> bool:
        """Return True iff a record of the build exists in the database"""

    def list_machines(self) -> list[str]:
        """Return a list of machine names"""

    def previous(
        self, build_id: BuildRecord, completed: bool = True
    ) -> BuildRecord | None:
        """Return the previous build in the db or None"""

    def next(self, build: BuildRecord, completed: bool = True) -> BuildRecord | None:
        """Return the next build in the db or None"""

    def latest(self, machine: str, completed: bool = False) -> BuildRecord | None:
        """Return the latest build for the given machine name.

        If `completed` is `True`, only consider completed builds.
        If no builds exist for the given machine name, return None.
        """

    def search(self, machine: str, field: str, key: str) -> Iterable[BuildRecord]:
        """search the given field for given machine

        field must be a BuildRecord field. Not all fields may be searchable, in which
        case ValueError is raised.
        """

    def count(self, machine: str | None = None) -> int:
        """Return the total number of builds

        If `machine` is given, return the total number of builds for the given machine
        """


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
