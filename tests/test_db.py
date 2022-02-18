"""Tests for the db module"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from gentoo_build_publisher.build import BuildID
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.models import BuildLog, BuildModel, BuildNote, KeptBuild

from .factories import BuildModelFactory, BuildRecordFactory


# pylint: disable=too-many-public-methods
class BuildDBTestCase(TestCase):
    def setUp(self):
        super().setUp()

        self.record = BuildRecordFactory()

    def test_id_property(self):
        self.assertTrue(isinstance(self.record.id, BuildID))

        # pylint: disable=protected-access
        self.assertEqual(self.record.id, self.record._build_id)

    def test_submitted_set(self):
        model = BuildDB.save(
            self.record, submitted=timezone.make_aware(datetime(1970, 1, 1))
        )

        self.assertEqual(model.submitted, timezone.make_aware(datetime(1970, 1, 1)))

    def test_completed_get(self):
        model = BuildModelFactory.create(
            completed=timezone.make_aware(datetime(1970, 1, 1))
        )

        record = BuildDB.model_to_record(model)

        self.assertEqual(record.completed, timezone.make_aware(datetime(1970, 1, 1)))

    def test_completed_set(self):
        BuildDB.save(self.record, completed=timezone.make_aware(datetime(1970, 1, 1)))

        model = BuildModel.objects.get(
            name=self.record.id.name, number=self.record.id.number
        )

        self.assertEqual(model.completed, timezone.make_aware(datetime(1970, 1, 1)))

    def test_save_note(self):
        record = self.record
        model = BuildDB.save(record, note="This is a test")

        build_note = BuildNote.objects.get(build_model=model)

        self.assertEqual(build_note.note, "This is a test")

    def test_delete_build_note(self):
        model = BuildDB.save(self.record)
        BuildNote.objects.create(build_model=model, note="This is a test")

        BuildDB.save(self.record, note=None)

        with self.assertRaises(BuildNote.DoesNotExist):
            BuildNote.objects.get(build_model=model)

    def test_save_keep(self):
        record = self.record
        model = BuildDB.save(record, keep=True)

        KeptBuild.objects.get(build_model=model)

    def test_delete_build_keep(self):
        model = BuildDB.save(self.record)
        KeptBuild.objects.create(build_model=model)

        BuildDB.save(self.record, keep=False)

        with self.assertRaises(KeptBuild.DoesNotExist):
            KeptBuild.objects.get(build_model=model)

    def test_save_logs(self):
        model = BuildDB.save(self.record, logs="This is a test")

        build_logs = BuildLog.objects.get(build_model=model)

        self.assertEqual(build_logs.logs, "This is a test")

    def test_delete_build_logs(self):
        model = BuildDB.save(self.record)
        BuildLog.objects.create(build_model=model, logs="This is a test")

        BuildDB.save(self.record, logs=None)

        with self.assertRaises(BuildLog.DoesNotExist):
            BuildLog.objects.get(build_model=model)

    def test_save_not_exists(self):
        record = BuildRecordFactory(build_id=BuildID("foo.555"))

        model = BuildDB.save(record)

        self.assertEqual(BuildModel.objects.get(name="foo", number=555), model)

    def test_save_exists(self):
        model = BuildModelFactory.create(
            name="foo", number=555, submitted=timezone.make_aware(datetime(1970, 1, 1))
        )

        record = BuildRecordFactory(build_id=BuildID("foo.555"))
        model2 = BuildDB.save(record)

        self.assertEqual(model, model2)

    def test_get(self):
        BuildModelFactory.create(
            name="foo", number=555, submitted=timezone.make_aware(datetime(1970, 1, 1))
        )

        build_id = BuildID("foo.555")
        record = BuildDB.get(build_id)

        self.assertEqual(record.id, build_id)
        self.assertEqual(record.submitted, timezone.make_aware(datetime(1970, 1, 1)))

    def test_get_does_not_exist(self):
        with self.assertRaises(BuildDB.NotFound):
            BuildDB.get(BuildID("bogus.955"))

    def test_get_records(self):
        BuildDB.save(BuildRecordFactory(build_id=BuildID("foo.555")))
        BuildDB.save(BuildRecordFactory(build_id=BuildID("foo.556")))
        BuildDB.save(BuildRecordFactory(build_id=BuildID("bar.555")))

        records = [*BuildDB.get_records(number=555)]

        self.assertEqual([i.id.name for i in records], ["bar", "foo"])

    def test_previous_build_should_return_none_when_there_are_none(self):
        BuildDB.save(self.record)

        previous = BuildDB.previous_build(self.record.id)

        self.assertIs(previous, None)

    def test_previous_build_when_not_completed_should_return_none(self):
        previous_build = self.record
        BuildDB.save(previous_build)
        record = BuildRecordFactory()
        BuildDB.save(record)

        assert previous_build.id.name == record.id.name

        self.assertIs(BuildDB.previous_build(record.id), None)

    def test_previous_build_when_not_completed_and_completed_arg_is_false(self):
        previous_build = self.record
        BuildDB.save(previous_build)
        record = BuildRecordFactory()
        BuildDB.save(record)

        assert previous_build.id.name == record.id.name

        self.assertEqual(
            BuildDB.previous_build(record.id, completed=False), previous_build
        )

    def test_previous_build_when_completed(self):
        previous_build = self.record
        BuildDB.save(previous_build, completed=timezone.now())

        current_build = BuildRecordFactory()
        BuildDB.save(current_build)

        assert previous_build.id.name == current_build.id.name

        self.assertEqual(BuildDB.previous_build(current_build.id), previous_build)

    def test_next_build_should_return_none_when_there_are_none(self):
        build_id = BuildID("bogus.1")
        next_build = BuildDB.next_build(build_id)

        self.assertIs(next_build, None)

    def test_next_build_when_not_completed_should_return_none(self):
        BuildDB.save(self.record)
        next_build = BuildRecordFactory()
        BuildDB.save(next_build)

        assert next_build.id.name == self.record.id.name

        self.assertIs(BuildDB.next_build(self.record.id), None)

    def test_next_build_when_not_completed_and_completed_arg_is_false(self):
        BuildDB.save(self.record)
        next_build = BuildRecordFactory()
        BuildDB.save(next_build)

        assert next_build.id.name == self.record.id.name

        self.assertEqual(
            BuildDB.next_build(self.record.id, completed=False), next_build
        )

    def test_next_build_when_completed(self):
        BuildDB.save(self.record)
        next_build = BuildRecordFactory()
        BuildDB.save(next_build, completed=timezone.now())

        assert next_build.id.name == self.record.id.name

        self.assertEqual(BuildDB.next_build(self.record.id), next_build)

    def test_list_machines(self):
        BuildModelFactory.create(name="lighthouse")
        BuildModelFactory.create(name="babette")
        BuildModelFactory.create(name="babette")

        machines = BuildDB.list_machines()

        self.assertEqual(machines, ["babette", "lighthouse"])

    def test_count_name(self):
        BuildModelFactory.create(name="lighthouse")
        BuildModelFactory.create(name="babette")
        BuildModelFactory.create(name="babette")

        self.assertEqual(BuildDB.count(), 3)
        self.assertEqual(BuildDB.count("lighthouse"), 1)
        self.assertEqual(BuildDB.count("bogus"), 0)

    def test_repr_buildrecord(self):
        self.assertEqual(repr(self.record), f"BuildRecord(build_id='{self.record.id}')")
