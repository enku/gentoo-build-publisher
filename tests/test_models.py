"""Unit tests for gbp models"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import datetime as dt

from gentoo_build_publisher.models import (
    BuildLog,
    BuildModel,
    BuildNote,
    DjangoDB,
    KeptBuild,
)
from gentoo_build_publisher.records import BuildRecord, RecordNotFound
from gentoo_build_publisher.types import Build

from . import TestCase
from .factories import BuildModelFactory, BuildRecordFactory


class BuildModelTestCase(TestCase):
    """Unit tests for the BuildModel"""

    def test_str(self) -> None:
        """str(build_model) should return the expected string"""
        build_model = BuildModelFactory()

        string = str(build_model)

        self.assertEqual(string, f"{build_model.machine}.{build_model.build_id}")

    def test_repr(self) -> None:
        """repr(build_model) should return the expected string"""
        build_model = BuildModelFactory(machine="test", build_id="test.1")

        string = repr(build_model)

        self.assertEqual(string, "BuildModel(machine='test', build_id='test.1')")


class KeptBuildTestCase(TestCase):
    """Unit tests for KeptBuild"""

    def test_str(self) -> None:
        build_model = BuildModelFactory.create()
        kept_build = KeptBuild.objects.create(build_model=build_model)

        self.assertEqual(str(kept_build), str(build_model))


class BuildNoteTestCase(TestCase):
    """Unit tests for BuildNote"""

    def test_str(self) -> None:
        """str(BuildNote) should return the note string"""
        build_model = BuildModelFactory.create()
        build_note = BuildNote(build_model=build_model, note="Test note")

        self.assertEqual(str(build_note), f"Notes for build {build_model}")

    def test_update_saves_note_text(self) -> None:
        build_model = BuildModelFactory.create()
        note_text = "hello, world"

        BuildNote.update(build_model, note_text)

        self.assertEqual(BuildNote.objects.get(build_model=build_model).note, note_text)

    def test_update_method_removes_model(self) -> None:
        build_model = BuildModelFactory.create()
        BuildNote.objects.create(build_model=build_model, note="test")

        BuildNote.update(build_model, None)

        self.assertIs(BuildNote.objects.filter(build_model=build_model).exists(), False)


class BuildLogTestCase(TestCase):
    """Unit tests for the BuildLog model"""

    def test_update_saves_note_text(self) -> None:
        build_model = BuildModelFactory.create()
        logs = "This is\na test"

        BuildLog.update(build_model, logs)

        build_log = BuildLog.objects.get(build_model=build_model)
        self.assertEqual(build_log.logs, logs)

    def test_update_method_removes_model(self) -> None:
        build_model = BuildModelFactory.create()
        BuildLog.objects.create(build_model=build_model, logs="This is a test")

        BuildLog.update(build_model, None)

        self.assertIs(BuildLog.objects.filter(build_model=build_model).exists(), False)


# pylint: disable=too-many-public-methods
class DjangoDBTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.records = DjangoDB()
        self.build_model = BuildModelFactory.create(
            submitted=dt.datetime(2022, 2, 20, 15, 47, tzinfo=dt.timezone.utc),
            completed=dt.datetime(2022, 2, 20, 15, 58, tzinfo=dt.timezone.utc),
            built=dt.datetime(2022, 2, 20, 15, 58, tzinfo=dt.timezone.utc),
        )
        BuildLog.objects.create(build_model=self.build_model, logs="This is a test")
        self.record = self.records.get(Build.from_id(str(self.build_model)))

    def test_submitted_set(self) -> None:
        record = self.record._replace(
            submitted=dt.datetime(2022, 2, 20, 16, 47, tzinfo=dt.timezone.utc)
        )
        self.records.save(record)

        self.build_model.refresh_from_db()

        self.assertEqual(
            self.build_model.submitted,
            dt.datetime(2022, 2, 20, 16, 47, tzinfo=dt.timezone.utc),
        )

    def test_completed_get(self) -> None:
        self.assertEqual(
            self.record.submitted,
            dt.datetime(2022, 2, 20, 15, 47, tzinfo=dt.timezone.utc),
        )

    def test_completed_set(self) -> None:
        record = self.record._replace(
            completed=dt.datetime(2022, 2, 20, 16, 47, tzinfo=dt.timezone.utc)
        )
        self.records.save(record)

        self.build_model.refresh_from_db()

        self.assertEqual(
            self.build_model.completed,
            dt.datetime(2022, 2, 20, 16, 47, tzinfo=dt.timezone.utc),
        )

    def test_save_note(self) -> None:
        record = self.record._replace(note="This is a test")
        self.records.save(record)

        self.build_model.refresh_from_db()

        self.assertEqual(self.build_model.buildnote.note, "This is a test")

    def test_delete_build_note(self) -> None:
        BuildNote.objects.create(build_model=self.build_model, note="This is a test")

        self.records.save(self.record, note=None)

        with self.assertRaises(BuildNote.DoesNotExist):
            BuildNote.objects.get(build_model=self.build_model)

    def test_save_keep(self) -> None:
        record = self.record
        self.records.save(record, keep=True)

        KeptBuild.objects.get(build_model=self.build_model)

    def test_delete_build_keep(self) -> None:
        KeptBuild.objects.create(build_model=self.build_model)

        self.records.save(self.record, keep=False)

        with self.assertRaises(KeptBuild.DoesNotExist):
            KeptBuild.objects.get(build_model=self.build_model)

    def test_save_logs(self) -> None:
        self.records.save(self.record, logs="New logs")

        build_logs = BuildLog.objects.get(build_model=self.build_model)

        self.assertEqual(build_logs.logs, "New logs")

    def test_delete_build_logs(self) -> None:
        self.records.save(self.record, logs=None)

        with self.assertRaises(BuildLog.DoesNotExist):
            BuildLog.objects.get(build_model=self.build_model)

    def test_save_not_exists(self) -> None:
        record = BuildRecordFactory()

        self.records.save(record)

        self.assertTrue(
            BuildModel.objects.filter(
                machine=record.machine, build_id=record.build_id
            ).exists()
        )

    def test_save_exists(self) -> None:
        record = self.records.get(self.record)
        self.records.save(record)
        build_model = BuildModel.objects.get(
            machine=record.machine, build_id=record.build_id
        )

        self.assertEqual(build_model, self.build_model)

    def test_get(self) -> None:
        build = Build.from_id(str(self.build_model))
        record = self.records.get(build)

        self.assertEqual(record.id, build.id)
        self.assertEqual(record.submitted, self.build_model.submitted)

    def test_get_does_not_exist(self) -> None:
        with self.assertRaises(RecordNotFound):
            self.records.get(Build("bogus", "955"))

    def test_previous_should_return_none_when_there_are_none(self) -> None:
        previous = self.records.previous(self.record)

        self.assertIs(previous, None)

    def test_previous_when_not_completed_should_return_none(self) -> None:
        previous_build = self.record
        self.records.save(previous_build, completed=None)
        record = BuildModelFactory().record()

        assert previous_build.machine == record.machine

        self.assertIs(self.records.previous(record), None)

    def test_previous_when_not_completed_and_completed_arg_is_false(self) -> None:
        previous_build = self.records.save(self.record, completed=None)
        record = BuildModelFactory().record()

        assert previous_build.machine == record.machine

        self.assertEqual(self.records.previous(record, completed=False), previous_build)

    def test_previous_when_completed(self) -> None:
        previous_build = self.build_model
        current_build = BuildModelFactory()

        assert previous_build.machine == current_build.machine

        current_build_record = current_build.record()
        self.assertEqual(self.records.previous(current_build_record), self.record)

    def test_next_should_return_none_when_there_are_none(self) -> None:
        build = BuildRecordFactory.build(machine="bogus", build_id="1")
        next_build = self.records.next(build)

        self.assertIs(next_build, None)

    def test_next_when_not_completed_should_return_none(self) -> None:
        next_build = BuildModelFactory()

        assert next_build.machine == self.build_model.machine

        self.assertIs(self.records.next(self.record), None)

    def test_next_when_not_completed_and_completed_arg_is_false(self) -> None:
        # You really can't/shouldn't have a build that's built date is set but it isn't
        # completed as BuildPublisher._update_build_metadata updates both fields
        # simultaneously, but...
        next_build = BuildModelFactory(
            built=dt.datetime(2022, 2, 21, 15, 58, tzinfo=dt.timezone.utc)
        )

        assert next_build.machine == self.build_model.machine

        next_build_record = next_build.record()
        self.assertEqual(
            self.records.next(self.record, completed=False), next_build_record
        )

    def test_next_when_completed(self) -> None:
        next_build = BuildModelFactory(
            completed=dt.datetime(2022, 2, 21, 15, 58, tzinfo=dt.timezone.utc),
            built=dt.datetime(2022, 2, 21, 15, 58, tzinfo=dt.timezone.utc),
        )

        assert next_build.machine == self.build_model.machine

        next_build_record = next_build.record()
        self.assertEqual(self.records.next(self.record), next_build_record)

    def test_list_machines(self) -> None:
        BuildModelFactory.create(machine="lighthouse")
        BuildModelFactory.create(machine="babette")
        BuildModelFactory.create(machine="babette")

        machines = self.records.list_machines()

        self.assertEqual(machines, ["babette", "lighthouse"])

    def test_count_machine(self) -> None:
        BuildModelFactory.create(machine="lighthouse")
        BuildModelFactory.create(machine="babette")
        BuildModelFactory.create(machine="babette")

        self.assertEqual(self.records.count(), 4)
        self.assertEqual(self.records.count("lighthouse"), 1)
        self.assertEqual(self.records.count("bogus"), 0)

    def test_for_machine_when_only_one_build(self) -> None:
        BuildModelFactory.create(machine="lighthouse")

        records = [*self.records.for_machine("lighthouse")]

        self.assertEqual(1, len(records))
        record = records[0]
        self.assertIsInstance(record, BuildRecord)

    def test_for_machine_when_only_many_builds(self) -> None:
        BuildModelFactory.create_batch(3, machine="lighthouse")
        BuildModelFactory.create_batch(2, machine="babette")

        records = [*self.records.for_machine("lighthouse")]

        self.assertEqual(3, len(records))
        self.assertTrue(all(i.machine == "lighthouse" for i in records))

    def test_for_machine_when_no_builds(self) -> None:
        records = [*self.records.for_machine("bogus")]

        self.assertEqual([], records)
