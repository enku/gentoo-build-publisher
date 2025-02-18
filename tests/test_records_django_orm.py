"""Tests for the Django ORM RecordDB implementation"""

# pylint: disable=missing-docstring
import datetime as dt
from dataclasses import replace

import unittest_fixtures as fixture
from gbp_testkit import DjangoTestCase as TestCase
from gbp_testkit.factories import BuildModelFactory, BuildRecordFactory

from gentoo_build_publisher.models import BuildLog, BuildModel, BuildNote, KeptBuild
from gentoo_build_publisher.records import BuildRecord, RecordNotFound
from gentoo_build_publisher.types import Build


# pylint: disable=too-many-public-methods
@fixture.requires("build_model", "records_db", "record")
class RecordDBTestCase(TestCase):
    options = {
        "records_backend": "django",
        "build_model": {
            "submitted": dt.datetime(2022, 2, 20, 15, 47, tzinfo=dt.UTC),
            "completed": dt.datetime(2022, 2, 20, 15, 58, tzinfo=dt.UTC),
            "built": dt.datetime(2022, 2, 20, 15, 58, tzinfo=dt.UTC),
        },
    }

    def test_submitted_set(self) -> None:
        record = replace(
            self.fixtures.record,
            submitted=dt.datetime(2022, 2, 20, 16, 47, tzinfo=dt.UTC),
        )
        self.fixtures.records_db.save(record)

        self.fixtures.build_model.refresh_from_db()

        self.assertEqual(
            self.fixtures.build_model.submitted,
            dt.datetime(2022, 2, 20, 16, 47, tzinfo=dt.UTC),
        )

    def test_completed_get(self) -> None:
        self.assertEqual(
            self.fixtures.record.submitted,
            dt.datetime(2022, 2, 20, 15, 47, tzinfo=dt.UTC),
        )

    def test_completed_set(self) -> None:
        record = replace(
            self.fixtures.record,
            completed=dt.datetime(2022, 2, 20, 16, 47, tzinfo=dt.UTC),
        )
        self.fixtures.records_db.save(record)

        self.fixtures.build_model.refresh_from_db()

        self.assertEqual(
            self.fixtures.build_model.completed,
            dt.datetime(2022, 2, 20, 16, 47, tzinfo=dt.UTC),
        )

    def test_save_note(self) -> None:
        record = replace(self.fixtures.record, note="This is a test")
        self.fixtures.records_db.save(record)

        self.fixtures.build_model.refresh_from_db()

        self.assertEqual(self.fixtures.build_model.buildnote.note, "This is a test")

    def test_delete_build_note(self) -> None:
        BuildNote.objects.create(
            build_model=self.fixtures.build_model, note="This is a test"
        )

        self.fixtures.records_db.save(self.fixtures.record, note=None)

        with self.assertRaises(BuildNote.DoesNotExist):
            BuildNote.objects.get(build_model=self.fixtures.build_model)

    def test_save_keep(self) -> None:
        record = self.fixtures.record
        self.fixtures.records_db.save(record, keep=True)

        KeptBuild.objects.get(build_model=self.fixtures.build_model)

    def test_delete_build_keep(self) -> None:
        KeptBuild.objects.create(build_model=self.fixtures.build_model)

        self.fixtures.records_db.save(self.fixtures.record, keep=False)

        with self.assertRaises(KeptBuild.DoesNotExist):
            KeptBuild.objects.get(build_model=self.fixtures.build_model)

    def test_save_logs(self) -> None:
        self.fixtures.records_db.save(self.fixtures.record, logs="New logs")

        build_logs = BuildLog.objects.get(build_model=self.fixtures.build_model)

        self.assertEqual(build_logs.logs, "New logs")

    def test_delete_build_logs(self) -> None:
        self.fixtures.records_db.save(self.fixtures.record, logs=None)

        with self.assertRaises(BuildLog.DoesNotExist):
            BuildLog.objects.get(build_model=self.fixtures.build_model)

    def test_save_not_exists(self) -> None:
        record = BuildRecordFactory()

        self.fixtures.records_db.save(record)

        self.assertTrue(
            BuildModel.objects.filter(
                machine=record.machine, build_id=record.build_id
            ).exists()
        )

    def test_save_exists(self) -> None:
        record = self.fixtures.records_db.get(self.fixtures.record)
        self.fixtures.records_db.save(record)
        build_model = BuildModel.objects.get(
            machine=record.machine, build_id=record.build_id
        )

        self.assertEqual(build_model, self.fixtures.build_model)

    def test_get(self) -> None:
        build = Build.from_id(str(self.fixtures.build_model))
        record = self.fixtures.records_db.get(build)

        self.assertEqual(record.id, build.id)
        self.assertEqual(record.submitted, self.fixtures.build_model.submitted)

    def test_get_does_not_exist(self) -> None:
        with self.assertRaises(RecordNotFound):
            self.fixtures.records_db.get(Build("bogus", "955"))

    def test_previous_should_return_none_when_there_are_none(self) -> None:
        previous = self.fixtures.records_db.previous(self.fixtures.record)

        self.assertIs(previous, None)

    def test_previous_when_not_completed_should_return_none(self) -> None:
        previous_build = self.fixtures.record
        self.fixtures.records_db.save(previous_build, completed=None)
        record = BuildModelFactory().record()

        self.assertEqual(previous_build.machine, record.machine)

        self.assertIs(self.fixtures.records_db.previous(record), None)

    def test_previous_when_not_completed_and_completed_arg_is_false(self) -> None:
        previous_build = self.fixtures.records_db.save(
            self.fixtures.record, completed=None
        )
        record = BuildModelFactory().record()

        self.assertEqual(previous_build.machine, record.machine)

        self.assertEqual(
            self.fixtures.records_db.previous(record, completed=False), previous_build
        )

    def test_previous_when_completed(self) -> None:
        previous_build = self.fixtures.build_model
        current_build = BuildModelFactory()

        self.assertEqual(previous_build.machine, current_build.machine)

        current_build_record = current_build.record()
        self.assertEqual(
            self.fixtures.records_db.previous(current_build_record),
            self.fixtures.record,
        )

    def test_next_should_return_none_when_there_are_none(self) -> None:
        build = BuildRecordFactory.build(machine="bogus", build_id="1")
        next_build = self.fixtures.records_db.next(build)

        self.assertIs(next_build, None)

    def test_next_when_not_completed_should_return_none(self) -> None:
        next_build = BuildModelFactory()

        self.assertEqual(next_build.machine, self.fixtures.build_model.machine)
        self.assertIs(self.fixtures.records_db.next(self.fixtures.record), None)

    def test_next_when_not_completed_and_completed_arg_is_false(self) -> None:
        # You really can't/shouldn't have a build that's built date is set but it isn't
        # completed as BuildPublisher._update_build_metadata updates both fields
        # simultaneously, but...
        next_build = BuildModelFactory(
            built=dt.datetime(2022, 2, 21, 15, 58, tzinfo=dt.UTC)
        )

        self.assertEqual(next_build.machine, self.fixtures.build_model.machine)

        next_build_record = next_build.record()
        self.assertEqual(
            self.fixtures.records_db.next(self.fixtures.record, completed=False),
            next_build_record,
        )

    def test_next_when_completed(self) -> None:
        next_build = BuildModelFactory(
            completed=dt.datetime(2022, 2, 21, 15, 58, tzinfo=dt.UTC),
            built=dt.datetime(2022, 2, 21, 15, 58, tzinfo=dt.UTC),
        )

        self.assertEqual(next_build.machine, self.fixtures.build_model.machine)

        next_build_record = next_build.record()
        self.assertEqual(
            self.fixtures.records_db.next(self.fixtures.record), next_build_record
        )

    def test_list_machines(self) -> None:
        BuildModelFactory.create(machine="lighthouse")
        BuildModelFactory.create(machine="babette")
        BuildModelFactory.create(machine="babette")

        machines = self.fixtures.records_db.list_machines()

        self.assertEqual(machines, ["babette", "lighthouse"])

    def test_count_machine(self) -> None:
        BuildModelFactory.create(machine="lighthouse")
        BuildModelFactory.create(machine="babette")
        BuildModelFactory.create(machine="babette")

        self.assertEqual(self.fixtures.records_db.count(), 4)
        self.assertEqual(self.fixtures.records_db.count("lighthouse"), 1)
        self.assertEqual(self.fixtures.records_db.count("bogus"), 0)

    def test_for_machine_when_only_one_build(self) -> None:
        BuildModelFactory.create(machine="lighthouse")

        records = [*self.fixtures.records_db.for_machine("lighthouse")]

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertIsInstance(record, BuildRecord)

    def test_for_machine_when_only_many_builds(self) -> None:
        BuildModelFactory.create_batch(3, machine="lighthouse")
        BuildModelFactory.create_batch(2, machine="babette")

        records = [*self.fixtures.records_db.for_machine("lighthouse")]

        self.assertEqual(3, len(records))
        self.assertTrue(all(i.machine == "lighthouse" for i in records))

    def test_for_machine_when_no_builds(self) -> None:
        records = [*self.fixtures.records_db.for_machine("bogus")]

        self.assertEqual([], records)
