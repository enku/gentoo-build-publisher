"""Tests for the types module"""
# pylint: disable=missing-docstring
import datetime as dt
from datetime import timezone
from pathlib import Path
from unittest import TestCase

from django.test import TestCase as DjangoTestCase

from gentoo_build_publisher.records import Records
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.types import (
    Build,
    BuildRecord,
    InvalidBuild,
    RecordDB,
    RecordNotFound,
)

from . import parametrized
from .factories import BuildRecordFactory

BACKENDS = [["django"]]
UTC = timezone.utc


class BuildTestCase(TestCase):
    def test_from_id_with_name_and_number(self) -> None:
        build = Build.from_id("babette.16")

        self.assertEqual(str(build), "babette.16")

    def test_from_id_with_no_name(self) -> None:
        with self.assertRaises(InvalidBuild):
            Build.from_id(".16")

    def test_has_machine_and_build_id_attrs(self) -> None:
        build = Build("babette", "16")

        self.assertEqual(build.machine, "babette")
        self.assertEqual(build.build_id, "16")

    def test_repr(self) -> None:
        build = Build("babette", "16")

        self.assertEqual("Build('babette.16')", repr(build))


class BuildRecordTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.record = BuildRecordFactory()

    def test_repr_buildrecord(self) -> None:
        self.assertEqual(repr(self.record), f"BuildRecord('{self.record}')")


class RecordDBTestCase(DjangoTestCase):
    def backend(self, backend_name: str) -> RecordDB:
        settings = Settings(
            RECORDS_BACKEND=backend_name,
            STORAGE_PATH=Path("/dev/null"),
            JENKINS_BASE_URL="http://jenkins.invalid/",
        )
        return Records.from_settings(settings)

    @parametrized(BACKENDS)
    def test_save(self, backend: str) -> None:
        records = self.backend(backend)
        timestamp = dt.datetime(2022, 9, 4, 9, 22, 0, 0, UTC)

        build_record = records.save(
            BuildRecord("lighthouse", "8924", completed=timestamp)
        )

        self.assertEqual(records.get(Build("lighthouse", "8924")), build_record)
        self.assertEqual(records.get(Build("lighthouse", "8924")).completed, timestamp)

    @parametrized(BACKENDS)
    def test_save_with_given_fields_updates_fields(self, backend: str) -> None:
        records = self.backend(backend)
        timestamp = dt.datetime(2022, 9, 4, 9, 22, 0, 0, UTC)

        build_record = BuildRecord("lighthouse", "8924", completed=timestamp)
        build_record = records.save(build_record, logs="Build succeeded!", keep=True)

        self.assertEqual(records.get(Build("lighthouse", "8924")), build_record)
        self.assertEqual(
            records.get(Build("lighthouse", "8924")).logs, "Build succeeded!"
        )
        self.assertEqual(records.get(Build("lighthouse", "8924")).keep, True)

    @parametrized(BACKENDS)
    def test_get(self, backend: str) -> None:
        records = self.backend(backend)
        build_record = records.save(BuildRecord("lighthouse", "8924"))

        self.assertEqual(records.get(Build("lighthouse", "8924")), build_record)

        with self.assertRaises(RecordNotFound):
            records.get(Build("anchor", "0"))

    @parametrized(BACKENDS)
    def test_for_machine(self, backend: str) -> None:
        records = self.backend(backend)
        builds: list[BuildRecord] = [
            records.save(BuildRecord("lighthouse", "8923")),
            records.save(BuildRecord("lighthouse", "8924")),
        ]

        self.assertListEqual([*records.for_machine("lighthouse")], [*reversed(builds)])
        self.assertListEqual([*records.for_machine("anchor")], [])

    @parametrized(BACKENDS)
    def test_delete(self, backend: str) -> None:
        build_record = BuildRecordFactory()
        records = self.backend(backend)
        records.save(build_record)
        self.assertTrue(records.exists(build_record))

        records.delete(build_record)

        self.assertFalse(records.exists(build_record))

    @parametrized(BACKENDS)
    def test_exists(self, backend: str) -> None:
        records = self.backend(backend)
        build_record = BuildRecord("lighthouse", "8924")
        records.save(build_record)
        bogus_build = Build("anchor", "0")

        self.assertIs(records.exists(Build("lighthouse", "8924")), True)
        self.assertIs(records.exists(bogus_build), False)

    @parametrized(BACKENDS)
    def test_list_machines(self, backend: str) -> None:
        records = self.backend(backend)
        self.assertEqual(records.list_machines(), [])

        records.save(BuildRecord("lighthouse", "8923"))
        records.save(BuildRecord("lighthouse", "8924"))
        records.save(BuildRecord("anchor", "1"))

        machines = records.list_machines()

        self.assertEqual(machines, ["anchor", "lighthouse"])

    @parametrized(BACKENDS)
    def test_previous(self, backend: str) -> None:
        records = self.backend(backend)
        build1 = BuildRecordFactory(
            built=dt.datetime.fromtimestamp(1662310204, UTC),
            completed=dt.datetime.fromtimestamp(1662311204, UTC),
        )
        records.save(build1)
        build2 = BuildRecordFactory(built=dt.datetime.fromtimestamp(1662315204, UTC))
        records.save(build2)

        self.assertEqual(records.previous(build2).id, build1.id)
        self.assertIsNone(records.previous(build1))
        self.assertIsNone(records.previous(BuildRecordFactory(machine="bogus")))

    @parametrized(BACKENDS)
    def test_next(self, backend: str) -> None:
        records = self.backend(backend)
        build1 = BuildRecordFactory(
            built=dt.datetime.fromtimestamp(1662310204, UTC),
        )
        records.save(build1)
        build2 = BuildRecordFactory(
            built=dt.datetime.fromtimestamp(1662315204, UTC),
            completed=dt.datetime.fromtimestamp(1662311204, UTC),
        )
        records.save(build2)

        self.assertEqual(records.next(build1).id, build2.id)
        self.assertIsNone(records.next(build2))
        self.assertIsNone(records.next(BuildRecordFactory(machine="bogus")))

    @parametrized(BACKENDS)
    def test_latest_with_completed_true(self, backend: str) -> None:
        records = self.backend(backend)
        build1 = BuildRecordFactory(
            machine="lighthouse",
            built=dt.datetime.fromtimestamp(1662310204, UTC),
        )
        records.save(build1)
        build2 = BuildRecordFactory(
            machine="lighthouse",
            built=dt.datetime.fromtimestamp(1662315204, UTC),
            completed=dt.datetime.fromtimestamp(1662311204, UTC),
        )
        records.save(build2)

        self.assertEqual(records.latest("lighthouse", completed=True).id, build2.id)

        records.delete(build2)
        self.assertEqual(records.latest("lighthouse", completed=True), None)

    @parametrized(BACKENDS)
    def test_latest_with_completed_false(self, backend: str) -> None:
        records = self.backend(backend)
        build1 = BuildRecordFactory(
            machine="lighthouse",
            built=dt.datetime.fromtimestamp(1662310204, UTC),
        )
        records.save(build1)
        build2 = BuildRecordFactory(
            machine="lighthouse",
            built=dt.datetime.fromtimestamp(1662315204, UTC),
            completed=dt.datetime.fromtimestamp(1662311204, UTC),
        )
        records.save(build2)

        self.assertEqual(records.latest("lighthouse", completed=False).id, build2.id)

        records.delete(build2)
        self.assertEqual(records.latest("lighthouse", completed=False).id, build1.id)

    @parametrized(BACKENDS)
    def test_search_notes(self, backend: str) -> None:
        records = self.backend(backend)
        build1 = BuildRecordFactory(
            machine="lighthouse",
            built=dt.datetime.fromtimestamp(1662310204, UTC),
            completed=dt.datetime.fromtimestamp(1662311204, UTC),
            note="foo",
        )
        records.save(build1)
        build2 = BuildRecordFactory(
            machine="lighthouse",
            built=dt.datetime.fromtimestamp(1662315204, UTC),
            completed=dt.datetime.fromtimestamp(1662311204, UTC),
            note="foobar",
        )
        records.save(build2)

        builds = records.search_notes("lighthouse", "foo")
        self.assertEqual([build.id for build in builds], [build2.id, build1.id])

        builds = records.search_notes("lighthouse", "bar")
        self.assertEqual([build.id for build in builds], [build2.id])

        builds = records.search_notes("bogus", "foo")
        self.assertEqual([build.id for build in builds], [])

    @parametrized(BACKENDS)
    def test_count(self, backend: str) -> None:
        records = self.backend(backend)
        today = dt.datetime(2022, 9, 4, 9, 22, 0, tzinfo=UTC)

        for i in reversed(range(4)):
            day = today - dt.timedelta(days=i)
            for machine in ["lighthouse", "blackwidow"]:
                builds = BuildRecordFactory.create_batch(2, machine=machine)

                for build in builds:
                    records.save(build, submitted=day)

        self.assertEqual(records.count(), 16)
        self.assertEqual(records.count("blackwidow"), 8)
        self.assertEqual(records.count("bogus"), 0)
