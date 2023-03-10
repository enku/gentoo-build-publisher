"""Memory-based RecordDB implementation"""
import datetime as dt
import typing as t
from collections.abc import Iterable
from dataclasses import replace
from datetime import timezone

from gentoo_build_publisher.common import Build
from gentoo_build_publisher.records import BuildRecord, RecordNotFound

BuildId = str
Machine = str


class RecordDB:
    """Memory-backed RecordDB

    Implements the RecordDB interface and stores BuildRecords in a dict of dicts with
    the following structure:

        {
            "anchor": {
                "1": BuildRecord("anchor.1")
            }
            "lighthouse": {
                "8923": BuildRecord('lighthouse.8923'),
                "8924": BuildRecord('lighthouse.8924')
            }
        }

    Where in the above example "anchor" and "lighthouse" are machine names.

    This backend can be used for testing.
    """

    def __init__(self) -> None:
        self.builds: dict[Machine, dict[BuildId, BuildRecord]] = {}

    def save(self, record: BuildRecord, **fields: t.Any) -> BuildRecord:
        """Save the given record to the db"""
        record = replace(record, **fields)

        if record.submitted is None:
            record = replace(record, submitted=dt.datetime.now(tz=timezone.utc))

        machine = record.machine

        if machine not in self.builds:
            self.builds[machine] = {record.build_id: record}
        else:
            self.builds[machine][record.build_id] = record

        return record

    def get(self, build: Build) -> BuildRecord:
        """Retrieve db record"""
        machine = build.machine

        builds = self.builds.get(machine, {})

        record_build = builds.get(build.build_id)

        if not record_build:
            raise RecordNotFound()

        return record_build

    def for_machine(self, machine: Machine) -> list[BuildRecord]:
        """Return BuildRecords for the given machine"""
        records = [*self.builds.get(machine, {}).values()]
        records.sort(reverse=True, key=record_key)

        return records

    def delete(self, build: Build) -> None:
        """Delete this Build from the db"""
        self.builds.get(build.machine, {}).pop(build.build_id, None)

    def exists(self, build: Build) -> bool:
        """Return true if `build` exists in the db"""
        machine_builds = self.builds.get(build.machine)

        if not machine_builds:
            return False

        return build.build_id in machine_builds

    def list_machines(self) -> list[Machine]:
        """Return a list of machine names"""
        machines = [*self.builds]
        machines.sort()

        return machines

    def previous(
        self, build: BuildRecord, completed: bool = True
    ) -> BuildRecord | None:
        """Return the previous build in the db or None"""
        machine = build.machine
        records = []

        for record in self.for_machine(machine):
            if completed and not record.completed:
                continue
            if not record.built:
                continue
            if build.built and record.built >= build.built:
                continue
            records.append(record)

        if not records:
            return None

        records.sort(key=record_key)

        return records[-1]

    def next(self, build: BuildRecord, completed: bool = True) -> BuildRecord | None:
        """Return the next build in the db or None"""
        machine = build.machine
        records = []

        for record in self.for_machine(machine):
            if record.build_id == build.build_id:
                continue
            if completed and not record.completed:
                continue
            if not record.built:
                continue
            if build.built and record.built < build.built:
                continue
            records.append(record)

        if not records:
            return None

        records.sort()

        return records[0]

    def latest(self, name: str, completed: bool = False) -> BuildRecord | None:
        """Return the latest build for the given machine name.

        If `completed` is `True`, only consider completed builds.
        If no builds exist for the given machine name, return None.
        """
        records = self.for_machine(name)

        if completed:
            records = [record for record in records if record.completed is not None]
        records.sort(key=record_key)

        if not records:
            return None

        return records[-1]

    def search_notes(self, machine: str, key: str) -> Iterable[BuildRecord]:
        """search notes for given machine"""
        key = key.lower()
        records = self.for_machine(machine)
        records.sort(key=record_key, reverse=True)

        for record in records:
            if record.note and key in record.note:
                yield record

    def count(self, name: str | None = None) -> int:
        """Return the total number of builds

        If `name` is given, return the total number of builds for the given machine
        """
        if name:
            return len(self.builds.get(name, {}))

        return sum(len(builds) for builds in self.builds.values())


def record_key(record: BuildRecord) -> int | str:
    """Sort key function for records (of the same machine)"""
    try:
        return int(record.build_id)
    except ValueError:
        return record.build_id
