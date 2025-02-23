"""Tests for the Django ORM RecordDB implementation"""

# pylint: disable=missing-docstring
import datetime as dt
from dataclasses import replace

from gbp_testkit import DjangoTestCase as TestCase
from gbp_testkit.factories import BuildModelFactory, BuildRecordFactory
from unittest_fixtures import Fixtures, given, where

from gentoo_build_publisher.models import BuildLog, BuildModel, BuildNote, KeptBuild
from gentoo_build_publisher.records import BuildRecord, RecordNotFound
from gentoo_build_publisher.types import Build


# pylint: disable=too-many-public-methods
@given("build_model", "records_db", "record")
@where(
    records_db__backend="django",
    build_model__submitted=dt.datetime(2022, 2, 20, 15, 47, tzinfo=dt.UTC),
    build_model__completed=dt.datetime(2022, 2, 20, 15, 58, tzinfo=dt.UTC),
    build_model__built=dt.datetime(2022, 2, 20, 15, 58, tzinfo=dt.UTC),
)
class RecordDBTestCase(TestCase):
    def test_submitted_set(self, fixtures: Fixtures) -> None:
        record = replace(
            fixtures.record, submitted=dt.datetime(2022, 2, 20, 16, 47, tzinfo=dt.UTC)
        )
        fixtures.records_db.save(record)

        fixtures.build_model.refresh_from_db()

        self.assertEqual(
            fixtures.build_model.submitted,
            dt.datetime(2022, 2, 20, 16, 47, tzinfo=dt.UTC),
        )

    def test_completed_get(self, fixtures: Fixtures) -> None:
        self.assertEqual(
            fixtures.record.submitted, dt.datetime(2022, 2, 20, 15, 47, tzinfo=dt.UTC)
        )

    def test_completed_set(self, fixtures: Fixtures) -> None:
        record = replace(
            fixtures.record, completed=dt.datetime(2022, 2, 20, 16, 47, tzinfo=dt.UTC)
        )
        fixtures.records_db.save(record)

        fixtures.build_model.refresh_from_db()

        self.assertEqual(
            fixtures.build_model.completed,
            dt.datetime(2022, 2, 20, 16, 47, tzinfo=dt.UTC),
        )

    def test_save_note(self, fixtures: Fixtures) -> None:
        record = replace(fixtures.record, note="This is a test")
        fixtures.records_db.save(record)

        fixtures.build_model.refresh_from_db()

        self.assertEqual(fixtures.build_model.buildnote.note, "This is a test")

    def test_delete_build_note(self, fixtures: Fixtures) -> None:
        BuildNote.objects.create(
            build_model=fixtures.build_model, note="This is a test"
        )

        fixtures.records_db.save(fixtures.record, note=None)

        with self.assertRaises(BuildNote.DoesNotExist):
            BuildNote.objects.get(build_model=fixtures.build_model)

    def test_save_keep(self, fixtures: Fixtures) -> None:
        record = fixtures.record
        fixtures.records_db.save(record, keep=True)

        KeptBuild.objects.get(build_model=fixtures.build_model)

    def test_delete_build_keep(self, fixtures: Fixtures) -> None:
        KeptBuild.objects.create(build_model=fixtures.build_model)

        fixtures.records_db.save(fixtures.record, keep=False)

        with self.assertRaises(KeptBuild.DoesNotExist):
            KeptBuild.objects.get(build_model=fixtures.build_model)

    def test_save_logs(self, fixtures: Fixtures) -> None:
        fixtures.records_db.save(fixtures.record, logs="New logs")

        build_logs = BuildLog.objects.get(build_model=fixtures.build_model)

        self.assertEqual(build_logs.logs, "New logs")

    def test_delete_build_logs(self, fixtures: Fixtures) -> None:
        fixtures.records_db.save(fixtures.record, logs=None)

        with self.assertRaises(BuildLog.DoesNotExist):
            BuildLog.objects.get(build_model=fixtures.build_model)

    def test_save_not_exists(self, fixtures: Fixtures) -> None:
        record = BuildRecordFactory()

        fixtures.records_db.save(record)

        self.assertTrue(
            BuildModel.objects.filter(
                machine=record.machine, build_id=record.build_id
            ).exists()
        )

    def test_save_exists(self, fixtures: Fixtures) -> None:
        record = fixtures.records_db.get(fixtures.record)
        fixtures.records_db.save(record)
        build_model = BuildModel.objects.get(
            machine=record.machine, build_id=record.build_id
        )

        self.assertEqual(build_model, fixtures.build_model)

    def test_get(self, fixtures: Fixtures) -> None:
        build = Build.from_id(str(fixtures.build_model))
        record = fixtures.records_db.get(build)

        self.assertEqual(record.id, build.id)
        self.assertEqual(record.submitted, fixtures.build_model.submitted)

    def test_get_does_not_exist(self, fixtures: Fixtures) -> None:
        with self.assertRaises(RecordNotFound):
            fixtures.records_db.get(Build("bogus", "955"))

    def test_previous_should_return_none_when_there_are_none(
        self, fixtures: Fixtures
    ) -> None:
        previous = fixtures.records_db.previous(fixtures.record)

        self.assertIs(previous, None)

    def test_previous_when_not_completed_should_return_none(
        self, fixtures: Fixtures
    ) -> None:
        previous_build = fixtures.record
        fixtures.records_db.save(previous_build, completed=None)
        record = BuildModelFactory().record()

        self.assertEqual(previous_build.machine, record.machine)

        self.assertIs(fixtures.records_db.previous(record), None)

    def test_previous_when_not_completed_and_completed_arg_is_false(
        self, fixtures: Fixtures
    ) -> None:
        previous_build = fixtures.records_db.save(fixtures.record, completed=None)
        record = BuildModelFactory().record()

        self.assertEqual(previous_build.machine, record.machine)

        self.assertEqual(
            fixtures.records_db.previous(record, completed=False), previous_build
        )

    def test_previous_when_completed(self, fixtures: Fixtures) -> None:
        previous_build = fixtures.build_model
        current_build = BuildModelFactory()

        self.assertEqual(previous_build.machine, current_build.machine)

        current_build_record = current_build.record()
        self.assertEqual(
            fixtures.records_db.previous(current_build_record), fixtures.record
        )

    def test_next_should_return_none_when_there_are_none(
        self, fixtures: Fixtures
    ) -> None:
        build = BuildRecordFactory.build(machine="bogus", build_id="1")
        next_build = fixtures.records_db.next(build)

        self.assertIs(next_build, None)

    def test_next_when_not_completed_should_return_none(
        self, fixtures: Fixtures
    ) -> None:
        next_build = BuildModelFactory()

        self.assertEqual(next_build.machine, fixtures.build_model.machine)
        self.assertIs(fixtures.records_db.next(fixtures.record), None)

    def test_next_when_not_completed_and_completed_arg_is_false(
        self, fixtures: Fixtures
    ) -> None:
        # You really can't/shouldn't have a build that's built date is set but it isn't
        # completed as BuildPublisher._update_build_metadata updates both fields
        # simultaneously, but...
        next_build = BuildModelFactory(
            built=dt.datetime(2022, 2, 21, 15, 58, tzinfo=dt.UTC)
        )

        self.assertEqual(next_build.machine, fixtures.build_model.machine)

        next_build_record = next_build.record()
        self.assertEqual(
            fixtures.records_db.next(fixtures.record, completed=False),
            next_build_record,
        )

    def test_next_when_completed(self, fixtures: Fixtures) -> None:
        next_build = BuildModelFactory(
            completed=dt.datetime(2022, 2, 21, 15, 58, tzinfo=dt.UTC),
            built=dt.datetime(2022, 2, 21, 15, 58, tzinfo=dt.UTC),
        )

        self.assertEqual(next_build.machine, fixtures.build_model.machine)

        next_build_record = next_build.record()
        self.assertEqual(fixtures.records_db.next(fixtures.record), next_build_record)

    def test_list_machines(self, fixtures: Fixtures) -> None:
        BuildModelFactory.create(machine="lighthouse")
        BuildModelFactory.create(machine="babette")
        BuildModelFactory.create(machine="babette")

        machines = fixtures.records_db.list_machines()

        self.assertEqual(machines, ["babette", "lighthouse"])

    def test_count_machine(self, fixtures: Fixtures) -> None:
        BuildModelFactory.create(machine="lighthouse")
        BuildModelFactory.create(machine="babette")
        BuildModelFactory.create(machine="babette")

        self.assertEqual(fixtures.records_db.count(), 4)
        self.assertEqual(fixtures.records_db.count("lighthouse"), 1)
        self.assertEqual(fixtures.records_db.count("bogus"), 0)

    def test_for_machine_when_only_one_build(self, fixtures: Fixtures) -> None:
        BuildModelFactory.create(machine="lighthouse")

        records = [*fixtures.records_db.for_machine("lighthouse")]

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertIsInstance(record, BuildRecord)

    def test_for_machine_when_only_many_builds(self, fixtures: Fixtures) -> None:
        BuildModelFactory.create_batch(3, machine="lighthouse")
        BuildModelFactory.create_batch(2, machine="babette")

        records = [*fixtures.records_db.for_machine("lighthouse")]

        self.assertEqual(3, len(records))
        self.assertTrue(all(i.machine == "lighthouse" for i in records))

    def test_for_machine_when_no_builds(self, fixtures: Fixtures) -> None:
        records = [*fixtures.records_db.for_machine("bogus")]

        self.assertEqual([], records)
