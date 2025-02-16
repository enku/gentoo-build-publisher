"""Tests for the db module"""

# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime as dt
import json
from itertools import product
from pathlib import Path

from django.test import TestCase
from unittest_fixtures import parametrized, requires

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

from .factories import BuildRecordFactory

BACKENDS = [["django"], ["memory"]]


@requires("tmpdir")
class RecordDBTestCase(TestCase):
    def backend(self, backend_name: str) -> RecordDB:
        settings = Settings(
            RECORDS_BACKEND=backend_name,
            STORAGE_PATH=Path("/dev/null"),
            JENKINS_BASE_URL="http://jenkins.invalid/",
        )
        return build_records(settings)

    @parametrized(BACKENDS)
    def test_save(self, backend: str) -> None:
        records = self.backend(backend)
        timestamp = dt.datetime(2022, 9, 4, 9, 22, 0, 0, dt.UTC)

        build_record = records.save(
            BuildRecord("lighthouse", "8924", completed=timestamp)
        )

        self.assertEqual(records.get(Build("lighthouse", "8924")), build_record)
        self.assertEqual(records.get(Build("lighthouse", "8924")).completed, timestamp)

    @parametrized(BACKENDS)
    def test_save_with_given_fields_updates_fields(self, backend: str) -> None:
        records = self.backend(backend)
        timestamp = dt.datetime(2022, 9, 4, 9, 22, 0, 0, dt.UTC)

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

        build = Build("anchor", "0")
        with self.assertRaises(RecordNotFound) as context:
            records.get(build)

        exception = context.exception
        self.assertEqual(exception.args, (build,))

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
            built=dt.datetime.fromtimestamp(1662310204, dt.UTC),
            completed=dt.datetime.fromtimestamp(1662311204, dt.UTC),
        )
        records.save(build1)
        build2 = BuildRecordFactory(built=dt.datetime.fromtimestamp(1662315204, dt.UTC))
        records.save(build2)

        self.assertEqual(records.previous(build2).id, build1.id)
        self.assertIsNone(records.previous(build1))
        self.assertIsNone(records.previous(BuildRecordFactory(machine="bogus")))

    @parametrized(BACKENDS)
    def test_next(self, backend: str) -> None:
        records = self.backend(backend)
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

    @parametrized(BACKENDS)
    def test_next_excludes_unbuilt(self, backend: str) -> None:
        records = self.backend(backend)
        build1 = BuildRecordFactory(built=dt.datetime.fromtimestamp(1662310204, dt.UTC))
        records.save(build1)
        build2 = BuildRecordFactory(
            built=None, completed=dt.datetime.fromtimestamp(1662311204, dt.UTC)
        )
        records.save(build2)

        self.assertEqual(records.next(build1), None)

    @parametrized(BACKENDS)
    def test_next_second_built_before_first(self, backend: str) -> None:
        records = self.backend(backend)
        build1 = BuildRecordFactory(built=dt.datetime.fromtimestamp(1662310204, dt.UTC))
        records.save(build1)

        build2 = BuildRecordFactory(
            built=build1.built - dt.timedelta(hours=1),
            completed=dt.datetime.fromtimestamp(1662311204, dt.UTC),
        )
        records.save(build2)

        self.assertEqual(records.next(build1), None)

    @parametrized(BACKENDS)
    def test_latest_with_completed_true(self, backend: str) -> None:
        records = self.backend(backend)
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

    @parametrized(BACKENDS)
    def test_latest_with_completed_false(self, backend: str) -> None:
        records = self.backend(backend)
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

    @parametrized(product(BACKENDS[0], ["logs", "note"]))
    def test_search(self, backend: str, field: str) -> None:
        records = self.backend(backend)
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

    @parametrized(BACKENDS)
    def test_search_unsearchable_field(self, backend: str) -> None:
        # Assume "machine" is an unsearchable field
        unsearchable = "machine"

        records = self.backend(backend)

        with self.assertRaises(ValueError):
            # pylint: disable=expression-not-assigned
            [*records.search("lighthouse", unsearchable, "foo")]

    @parametrized(BACKENDS)
    def test_count(self, backend: str) -> None:
        records = self.backend(backend)
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

    @parametrized(BACKENDS)
    def test_dump(self, backend: str) -> None:
        records = self.backend(backend)
        build = BuildRecordFactory.create()

        records.save(build)
        path = self.fixtures.tmpdir / "records.json"
        with open(path, "wb") as outfile:
            records.dump([build], outfile)

        with open(path, "rb") as infile:
            dump = json.load(infile)

        self.assertEqual([build], [BuildRecord(**item) for item in dump])

    @parametrized(BACKENDS)
    def test_restore(self, backend: str) -> None:
        records = self.backend(backend)
        record = BuildRecordFactory.create()
        record = records.save(record)
        path = self.fixtures.tmpdir / "records.json"

        with open(path, "wb") as outfile:
            records.dump([record], outfile)

        records.delete(record)

        with open(path, "rb") as infile:
            response = records.restore(infile)

        self.assertEqual([record], response)
        self.assertEqual(
            record, records.get(Build(machine=record.machine, build_id=record.build_id))
        )


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


class ApiKeyDBTests(TestCase):
    def backend(self, backend_name: str) -> ApiKeyDB:
        settings = Settings(
            RECORDS_BACKEND=backend_name,
            STORAGE_PATH=Path("/dev/null"),
            JENKINS_BASE_URL="http://jenkins.invalid/",
        )
        return api_keys(settings)

    @parametrized(BACKENDS)
    def test_list(self, backend: str) -> None:
        records = self.backend(backend)
        key1 = ApiKey(name="key1", key="foo", created=dt.datetime.now(tz=dt.UTC))
        records.save(key1)
        key2 = ApiKey(name="key2", key="bar", created=dt.datetime.now(tz=dt.UTC))
        records.save(key2)

        keys = records.list()

        self.assertEqual(keys, [key1, key2])

    @parametrized(BACKENDS)
    def test_get(self, backend: str) -> None:
        records = self.backend(backend)
        key = ApiKey(name="key1", key="foo", created=dt.datetime.now(tz=dt.UTC))
        records.save(key)

        self.assertEqual(records.get("key1"), key)

    @parametrized(BACKENDS)
    def test_get_does_not_exist(self, backend: str) -> None:
        records = self.backend(backend)

        with self.assertRaises(RecordNotFound):
            records.get("bogus")

    @parametrized(BACKENDS)
    def test_save(self, backend: str) -> None:
        records = self.backend(backend)
        key = ApiKey(name="key1", key="foo", created=dt.datetime.now(tz=dt.UTC))
        records.save(key)

        self.assertEqual(records.get("key1"), key)

    @parametrized(BACKENDS)
    def test_delete(self, backend: str) -> None:
        records = self.backend(backend)
        name = "key1"
        key = ApiKey(name=name, key="foo", created=dt.datetime.now(tz=dt.UTC))
        records.save(key)

        records.delete(name)

        with self.assertRaises(RecordNotFound):
            records.get(name)

    @parametrized(BACKENDS)
    def test_delete_when_does_not_exist(self, backend: str) -> None:
        records = self.backend(backend)

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


class RepoTests(TestCase):
    @parametrized(BACKENDS)
    def test_from_settings(self, backend: str) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            STORAGE_PATH=Path("/dev/null"),
            RECORDS_BACKEND=backend,
        )
        repo = Repo.from_settings(settings)
        build_records_type = type(repo.build_records)

        self.assertIn(backend, build_records_type.__module__)
