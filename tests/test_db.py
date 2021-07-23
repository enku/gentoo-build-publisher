"""Tests for the db module"""
# pylint: disable=missing-class-docstring,missing-function-docstring
import uuid
from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from gentoo_build_publisher.build import Build
from gentoo_build_publisher.db import BuildDB
from gentoo_build_publisher.models import BuildLog, BuildModel, BuildNote, KeptBuild

from .factories import BuildDBFactory, BuildModelFactory


# pylint: disable=too-many-public-methods
class BuildDBTestCase(TestCase):
    def setUp(self):
        super().setUp()

        self.build_db = BuildDBFactory.create()

    def test_id_property(self):
        self.assertEqual(self.build_db.id, self.build_db.model.id)

    def test_name_getter(self):
        self.assertEqual(self.build_db.name, self.build_db.model.name)

    def test_name_setter(self):
        self.build_db.name = "foo"
        self.build_db.save()

        build_model = BuildModel.objects.get(id=self.build_db.id)

        self.assertEqual(build_model.name, "foo")

    def test_number_getter(self):
        self.assertEqual(self.build_db.number, self.build_db.model.number)

    def test_number_setter(self):
        self.build_db.number = 100000
        self.build_db.save()

        build_model = BuildModel.objects.get(id=self.build_db.id)

        self.assertEqual(build_model.number, 100000)

    def test_submitted_setter(self):
        self.build_db.submitted = timezone.make_aware(datetime(1970, 1, 1))
        self.build_db.save()

        build_model = BuildModel.objects.get(id=self.build_db.id)

        self.assertEqual(
            build_model.submitted, timezone.make_aware(datetime(1970, 1, 1))
        )

    def test_completed_getter(self):
        build_model = BuildModelFactory.create(
            completed=timezone.make_aware(datetime(1970, 1, 1))
        )

        build_db = BuildDB(build_model=build_model)

        self.assertEqual(build_db.completed, timezone.make_aware(datetime(1970, 1, 1)))

    def test_completed_setter(self):
        self.build_db.completed = timezone.make_aware(datetime(1970, 1, 1))
        self.build_db.save()

        build_model = BuildModel.objects.get(id=self.build_db.id)

        self.assertEqual(
            build_model.completed, timezone.make_aware(datetime(1970, 1, 1))
        )

    def test_task_id_getter(self):
        build_model = BuildModelFactory.create(
            task_id="5288c012-fa72-42ef-ab4b-437b2110d75c"
        )

        build_db = BuildDB(build_model=build_model)

        self.assertEqual(build_db.task_id, "5288c012-fa72-42ef-ab4b-437b2110d75c")

    def test_task_id_setter(self):
        self.build_db.task_id = "5288c012-fa72-42ef-ab4b-437b2110d75c"
        self.build_db.save()

        build_model = BuildModel.objects.get(id=self.build_db.id)

        self.assertEqual(
            build_model.task_id, uuid.UUID("5288c012-fa72-42ef-ab4b-437b2110d75c")
        )

    def test_refesh(self):
        build_model = self.build_db.model

        BuildNote.objects.create(build_model=build_model, note="This is a test")

        self.build_db.refresh()

        self.assertEqual(self.build_db.note, "This is a test")

    def test_save_note(self):
        build_db = self.build_db
        build_db.note = "This is a test"
        build_db.save()

        build_note = BuildNote.objects.get(build_model=build_db.model)

        self.assertEqual(build_note.note, "This is a test")

    def test_delete_build_note(self):
        build_model = self.build_db.model
        BuildNote.objects.create(build_model=build_model, note="This is a test")

        self.build_db.note = None
        self.build_db.save()

        with self.assertRaises(BuildNote.DoesNotExist):
            BuildNote.objects.get(build_model=build_model)

    def test_delete_should_not_delete_when_model_has_no_pk(
        self,
    ):  # pylint: disable=no-self-use
        build_model = BuildModel(name="babette", number=286)
        build_db = BuildDB(build_model)

        build_db.delete()

    def test_save_keep(self):
        build_db = self.build_db
        build_db.keep = True
        build_db.save()

        KeptBuild.objects.get(build_model=build_db.model)

    def test_delete_build_keep(self):
        build_model = self.build_db.model
        KeptBuild.objects.create(build_model=build_model)

        self.build_db.keep = False
        self.build_db.save()

        with self.assertRaises(KeptBuild.DoesNotExist):
            KeptBuild.objects.get(build_model=build_model)

    def test_save_logs(self):
        build_db = self.build_db
        build_db.logs = "This is a test"
        build_db.save()

        build_logs = BuildLog.objects.get(build_model=build_db.model)

        self.assertEqual(build_logs.logs, "This is a test")

    def test_delete_build_logs(self):
        build_model = self.build_db.model
        BuildLog.objects.create(build_model=build_model, logs="This is a test")

        self.build_db.logs = None
        self.build_db.save()

        with self.assertRaises(BuildLog.DoesNotExist):
            BuildLog.objects.get(build_model=build_model)

    def test_create_not_exists(self):
        build_db = BuildDB.create(Build(name="foo", number=555))

        build_model = BuildModel.objects.get(name="foo", number=555)

        self.assertEqual(build_db.model, build_model)

    def test_create_exists(self):
        build_model = BuildModel.objects.create(
            name="foo", number=555, submitted=timezone.make_aware(datetime(1970, 1, 1))
        )

        build_db = BuildDB.create(Build(name="foo", number=555))

        self.assertEqual(build_db.model, build_model)

    def test_get(self):
        build_model = BuildModel.objects.create(
            name="foo", number=555, submitted=timezone.make_aware(datetime(1970, 1, 1))
        )

        build_db = BuildDB.get(Build(name="foo", number=555))

        self.assertEqual(build_db.model, build_model)

    def test_get_does_not_exist(self):
        with self.assertRaises(BuildDB.NotFound):
            BuildDB.get(Build(name="bogus", number=555))

    def test_builds(self):
        BuildDB.create(Build(name="foo", number=555))
        BuildDB.create(Build(name="foo", number=556))
        BuildDB.create(Build(name="bar", number=555))

        builds = list(BuildDB.builds(number=555))

        self.assertEqual([i.name for i in builds], ["bar", "foo"])

    def test_previous_build_should_return_none_when_there_are_none(self):
        build_db = self.build_db

        previous = build_db.previous_build()

        self.assertIs(previous, None)

    def test_previous_build_when_not_completed_should_return_none(self):
        previous_build = self.build_db
        build_db = BuildDBFactory()

        assert previous_build.name == build_db.name

        self.assertIs(build_db.previous_build(), None)

    def test_previous_build_when_not_completed_and_completed_arg_is_false(self):
        previous_build = self.build_db
        build_db = BuildDBFactory()

        assert previous_build.name == build_db.name

        self.assertEqual(build_db.previous_build(completed=False), previous_build)

    def test_previous_build_when_completed(self):
        previous_build = self.build_db
        previous_build.model.completed = timezone.now()
        previous_build.model.save()

        build_db = BuildDBFactory()

        assert previous_build.name == build_db.name

        self.assertEqual(build_db.previous_build(), previous_build)

    def test_next_build_should_return_none_when_there_are_none(self):
        build_db = self.build_db

        next_build = build_db.next_build()

        self.assertIs(next_build, None)

    def test_next_build_when_not_completed_should_return_none(self):
        next_build = self.build_db
        build_db = BuildDBFactory()

        assert next_build.name == build_db.name

        self.assertIs(build_db.next_build(), None)

    def test_next_build_when_not_completed_and_completed_arg_is_false(self):
        build_db = self.build_db
        next_build = BuildDBFactory()

        assert next_build.name == build_db.name

        self.assertEqual(build_db.next_build(completed=False), next_build)

    def test_next_build_when_completed(self):
        build_db = self.build_db
        next_build = BuildDBFactory()
        next_build.model.completed = timezone.now()
        next_build.model.save()

        assert next_build.name == build_db.name

        self.assertEqual(build_db.next_build(), next_build)

    def test_list_machines(self):
        BuildDBFactory.create(build_model__name="lighthouse")
        BuildDBFactory.create(build_model__name="babette")
        BuildDBFactory.create(build_model__name="babette")

        machines = BuildDB.list_machines()

        self.assertEqual(machines, ["babette", "lighthouse"])

    def test_count_name(self):
        BuildDBFactory.create(build_model__name="lighthouse")
        BuildDBFactory.create(build_model__name="babette")
        BuildDBFactory.create(build_model__name="babette")

        self.assertEqual(BuildDB.count(), 4)
        self.assertEqual(BuildDB.count("lighthouse"), 1)
        self.assertEqual(BuildDB.count("bogus"), 0)
