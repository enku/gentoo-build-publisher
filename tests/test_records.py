"""Tests for the db module"""

# pylint: disable=missing-class-docstring,missing-function-docstring,unused-argument
import datetime as dt
from pathlib import Path

import unittest_fixtures as uf
from django.test import TestCase

from gbp_testkit.factories import BuildRecordFactory
from gentoo_build_publisher.records import (
    ApiKeyDB,
    BuildRecord,
    RecordDB,
    RecordNotFound,
    Repo,
    api_keys,
    build_records,
)
from gentoo_build_publisher.records.django_orm import RecordDB as DjangoDB
from gentoo_build_publisher.records.memory import ApiKeyDB as MemoryApiKeyDB
from gentoo_build_publisher.records.memory import RecordDB as MemoryDB
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.types import ApiKey, Build

Fixtures = uf.Fixtures


@uf.fixture()
def build_records_fixture(_: Fixtures, backend: str = "memory") -> RecordDB:
    settings = Settings(
        RECORDS_BACKEND=backend,
        STORAGE_PATH=Path("/dev/null"),
        JENKINS_BASE_URL="http://jenkins.invalid/",
    )
    return build_records(settings)


@uf.given(records=build_records_fixture)
@uf.where(records__backend=uf.Param(lambda fixtures: fixtures.backend))
@uf.params(backend=("django", "memory"))
class RecordDBTestCase(TestCase):
    def test_save(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        timestamp = dt.datetime(2022, 9, 4, 9, 22, 0, 0, dt.UTC)

        build_record = records.save(
            BuildRecord("lighthouse", "8924", completed=timestamp)
        )

        self.assertEqual(records.get(Build("lighthouse", "8924")), build_record)
        self.assertEqual(records.get(Build("lighthouse", "8924")).completed, timestamp)

    def test_save_with_given_fields_updates_fields(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        timestamp = dt.datetime(2022, 9, 4, 9, 22, 0, 0, dt.UTC)

        build_record = BuildRecord("lighthouse", "8924", completed=timestamp)
        build_record = records.save(build_record, logs="Build succeeded!", keep=True)

        self.assertEqual(records.get(Build("lighthouse", "8924")), build_record)
        self.assertEqual(
            records.get(Build("lighthouse", "8924")).logs, "Build succeeded!"
        )
        self.assertEqual(records.get(Build("lighthouse", "8924")).keep, True)

    def test_get(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        build_record = records.save(BuildRecord("lighthouse", "8924"))

        self.assertEqual(records.get(Build("lighthouse", "8924")), build_record)

        build = Build("anchor", "0")
        with self.assertRaises(RecordNotFound) as context:
            records.get(build)

        exception = context.exception
        self.assertEqual(exception.args, (build,))

    def test_for_machine(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        builds: list[BuildRecord] = [
            records.save(BuildRecord("lighthouse", "8923")),
            records.save(BuildRecord("lighthouse", "8924")),
        ]

        self.assertListEqual([*records.for_machine("lighthouse")], [*reversed(builds)])
        self.assertListEqual([*records.for_machine("anchor")], [])

    def test_delete(self, fixtures: Fixtures) -> None:
        build_record = BuildRecordFactory()
        records = fixtures.records
        records.save(build_record)
        self.assertTrue(records.exists(build_record))

        records.delete(build_record)

        self.assertFalse(records.exists(build_record))

    def test_exists(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        build_record = BuildRecord("lighthouse", "8924")
        records.save(build_record)
        bogus_build = Build("anchor", "0")

        self.assertIs(records.exists(Build("lighthouse", "8924")), True)
        self.assertIs(records.exists(bogus_build), False)

    def test_list_machines(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        self.assertEqual(records.list_machines(), [])

        records.save(BuildRecord("lighthouse", "8923"))
        records.save(BuildRecord("lighthouse", "8924"))
        records.save(BuildRecord("anchor", "1"))

        machines = records.list_machines()

        self.assertEqual(machines, ["anchor", "lighthouse"])

    def test_previous(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        build1 = BuildRecordFactory(
            built=dt.datetime.fromtimestamp(1662310204, dt.UTC),
            completed=dt.datetime.fromtimestamp(1662311204, dt.UTC),
        )
        records.save(build1)
        build2 = BuildRecordFactory(built=dt.datetime.fromtimestamp(1662315204, dt.UTC))
        records.save(build2)

        self.assertEqual(records.previous(build2).id, build1.id)
        self.assertIsNone(records.previous(build1))
        self.assertIsNone(records.previous(BuildRecordFactory(machine="bogus")))

    def test_next(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        build1 = BuildRecordFactory(built=dt.datetime.fromtimestamp(1662310204, dt.UTC))
        records.save(build1)
        build2 = BuildRecordFactory(
            built=dt.datetime.fromtimestamp(1662315204, dt.UTC),
            completed=dt.datetime.fromtimestamp(1662311204, dt.UTC),
        )
        records.save(build2)

        self.assertEqual(records.next(build1).id, build2.id)
        self.assertIsNone(records.next(build2))
        self.assertIsNone(records.next(BuildRecordFactory(machine="bogus")))

    def test_next_excludes_unbuilt(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        build1 = BuildRecordFactory(built=dt.datetime.fromtimestamp(1662310204, dt.UTC))
        records.save(build1)
        build2 = BuildRecordFactory(
            built=None, completed=dt.datetime.fromtimestamp(1662311204, dt.UTC)
        )
        records.save(build2)

        self.assertEqual(records.next(build1), None)

    def test_next_second_built_before_first(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        build1 = BuildRecordFactory(built=dt.datetime.fromtimestamp(1662310204, dt.UTC))
        records.save(build1)

        build2 = BuildRecordFactory(
            built=build1.built - dt.timedelta(hours=1),
            completed=dt.datetime.fromtimestamp(1662311204, dt.UTC),
        )
        records.save(build2)

        self.assertEqual(records.next(build1), None)

    def test_latest_with_completed_true(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        build1 = BuildRecordFactory(
            machine="lighthouse", built=dt.datetime.fromtimestamp(1662310204, dt.UTC)
        )
        records.save(build1)
        build2 = BuildRecordFactory(
            machine="lighthouse",
            built=dt.datetime.fromtimestamp(1662315204, dt.UTC),
            completed=dt.datetime.fromtimestamp(1662311204, dt.UTC),
        )
        records.save(build2)

        self.assertEqual(records.latest("lighthouse", completed=True).id, build2.id)

        records.delete(build2)
        self.assertEqual(records.latest("lighthouse", completed=True), None)

    def test_latest_with_completed_false(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        build1 = BuildRecordFactory(
            machine="lighthouse", built=dt.datetime.fromtimestamp(1662310204, dt.UTC)
        )
        records.save(build1)
        build2 = BuildRecordFactory(
            machine="lighthouse",
            built=dt.datetime.fromtimestamp(1662315204, dt.UTC),
            completed=dt.datetime.fromtimestamp(1662311204, dt.UTC),
        )
        records.save(build2)

        self.assertEqual(records.latest("lighthouse", completed=False).id, build2.id)

        records.delete(build2)
        self.assertEqual(records.latest("lighthouse", completed=False).id, build1.id)

    @uf.parametrized([["logs"], ["note"]])
    def test_search(self, field: str, fixtures: Fixtures) -> None:
        records = fixtures.records
        build1 = BuildRecordFactory(
            **{
                "built": dt.datetime.fromtimestamp(1662310204, dt.UTC),
                "completed": dt.datetime.fromtimestamp(1662311204, dt.UTC),
                "machine": "lighthouse",
                field: "foo",
            }
        )
        records.save(build1)
        build2 = BuildRecordFactory(
            **{
                "built": dt.datetime.fromtimestamp(1662310204, dt.UTC),
                "completed": dt.datetime.fromtimestamp(1662311204, dt.UTC),
                "machine": "lighthouse",
                field: "foobar",
            }
        )
        records.save(build2)

        builds = records.search("lighthouse", field, "foo")
        self.assertEqual([build.id for build in builds], [build2.id, build1.id])

        builds = records.search("lighthouse", field, "bar")
        self.assertEqual([build.id for build in builds], [build2.id])

        builds = records.search("bogus", field, "foo")
        self.assertEqual([build.id for build in builds], [])

    def test_search_unsearchable_field(self, fixtures: Fixtures) -> None:
        # Assume "machine" is an unsearchable field
        unsearchable = "machine"

        records = fixtures.records

        with self.assertRaises(ValueError):
            # pylint: disable=expression-not-assigned
            [*records.search("lighthouse", unsearchable, "foo")]

    def test_count(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        today = dt.datetime(2022, 9, 4, 9, 22, 0, tzinfo=dt.UTC)

        for i in reversed(range(4)):
            day = today - dt.timedelta(days=i)
            for machine in ["lighthouse", "blackwidow"]:
                builds = BuildRecordFactory.create_batch(2, machine=machine)

                for build in builds:
                    records.save(build, submitted=day)

        self.assertEqual(records.count(), 16)
        self.assertEqual(records.count("blackwidow"), 8)
        self.assertEqual(records.count("bogus"), 0)


class BuildRecordsTestCase(TestCase):
    def test_django(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            STORAGE_PATH=Path("/dev/null"),
            RECORDS_BACKEND="django",
        )

        recorddb = build_records(settings)
        self.assertIsInstance(recorddb, DjangoDB)

    def test_memory(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            STORAGE_PATH=Path("/dev/null"),
            RECORDS_BACKEND="memory",
        )

        recorddb = build_records(settings)
        self.assertIsInstance(recorddb, MemoryDB)

    def test_unknown_records_backend(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            STORAGE_PATH=Path("/dev/null"),
            RECORDS_BACKEND="bogus_backend",
        )

        with self.assertRaises(LookupError):
            build_records(settings)


def apikey_db_fixture(_: Fixtures, backend: str = "memory") -> ApiKeyDB:
    settings = Settings(
        RECORDS_BACKEND=backend,
        STORAGE_PATH=Path("/dev/null"),
        JENKINS_BASE_URL="http://jenkins.invalid/",
    )
    return api_keys(settings)


@uf.given(records=apikey_db_fixture)
@uf.params(backend=("django", "memory"))
@uf.where(records__backend=uf.Param(lambda fixtures: fixtures.backend))
class ApiKeyDBTests(TestCase):
    def test_list(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        key1 = ApiKey(name="key1", key="foo", created=dt.datetime.now(tz=dt.UTC))
        records.save(key1)
        key2 = ApiKey(name="key2", key="bar", created=dt.datetime.now(tz=dt.UTC))
        records.save(key2)

        keys = records.list()

        self.assertEqual(keys, [key1, key2])

    def test_get(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        key = ApiKey(name="key1", key="foo", created=dt.datetime.now(tz=dt.UTC))
        records.save(key)

        self.assertEqual(records.get("key1"), key)

    def test_get_does_not_exist(self, fixtures: Fixtures) -> None:
        records = fixtures.records

        with self.assertRaises(RecordNotFound):
            records.get("bogus")

    def test_save(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        key = ApiKey(name="key1", key="foo", created=dt.datetime.now(tz=dt.UTC))
        records.save(key)

        self.assertEqual(records.get("key1"), key)

    def test_delete(self, fixtures: Fixtures) -> None:
        records = fixtures.records
        name = "key1"
        key = ApiKey(name=name, key="foo", created=dt.datetime.now(tz=dt.UTC))
        records.save(key)

        records.delete(name)

        with self.assertRaises(RecordNotFound):
            records.get(name)

    def test_delete_when_does_not_exist(self, fixtures: Fixtures) -> None:
        records = fixtures.records

        with self.assertRaises(RecordNotFound):
            records.delete("bogus")


class ApiKeysTests(TestCase):
    def test_returns_requested_class(self) -> None:
        settings = Settings(
            RECORDS_BACKEND="memory",
            STORAGE_PATH=Path("/dev/null"),
            JENKINS_BASE_URL="http://jenkins.invalid/",
        )
        obj = api_keys(settings)

        self.assertIsInstance(obj, MemoryApiKeyDB)

    def test_raises_lookuperror(self) -> None:
        settings = Settings(
            RECORDS_BACKEND="bogus",
            STORAGE_PATH=Path("/dev/null"),
            JENKINS_BASE_URL="http://jenkins.invalid/",
        )

        with self.assertRaises(LookupError):
            api_keys(settings)


@uf.params(backend=("django", "memory"))
class RepoTests(TestCase):
    def test_from_settings(self, fixtures: Fixtures) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            STORAGE_PATH=Path("/dev/null"),
            RECORDS_BACKEND=fixtures.backend,
        )
        repo = Repo.from_settings(settings)
        build_records_type = type(repo.build_records)

        self.assertIn(fixtures.backend, build_records_type.__module__)
