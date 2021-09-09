"""Unit tests for gbp models"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from django.test import TestCase

from gentoo_build_publisher.models import BuildLog, BuildNote, KeptBuild

from . import TempHomeMixin
from .factories import BuildModelFactory


class BuildModelTestCase(TempHomeMixin, TestCase):
    """Unit tests for the BuildModel"""

    def test_str(self):
        """str(build_model) should return the expected string"""
        build_model = BuildModelFactory()

        string = str(build_model)

        self.assertEqual(string, f"{build_model.name}.{build_model.number}")

    def test_repr(self):
        """repr(build_model) should return the expected string"""
        build_model = BuildModelFactory(name="test", number=1)

        string = repr(build_model)

        self.assertEqual(string, "BuildModel(name='test', number=1)")


class KeptBuildTestCase(TempHomeMixin, TestCase):
    """Unit tests for KeptBuild"""

    def test_str(self):
        build_model = BuildModelFactory.create()
        kept_build = KeptBuild.objects.create(build_model=build_model)

        self.assertEqual(str(kept_build), str(build_model))


class BuildNoteTestCase(TempHomeMixin, TestCase):
    """Unit tests for BuildNote"""

    def test_str(self):
        """str(BuildNote) should return the note string"""
        build_model = BuildModelFactory.create()
        build_note = BuildNote(build_model=build_model, note="Test note")

        self.assertEqual(str(build_note), f"Notes for build {build_model}")

    def test_upsert_saves_note_text(self):
        build_model = BuildModelFactory.create()
        note_text = "hello, world"

        build_note = BuildNote.upsert(build_model, note_text)

        self.assertEqual(build_note.note, note_text)

    def test_remove_method_returns_false_when_no_note_exists(self):
        build_model = BuildModelFactory.create()

        deleted = BuildNote.remove(build_model)

        self.assertIs(deleted, False)

    def test_remove_method_returns_true_when_note_exists(self):
        build_model = BuildModelFactory.create()
        build_note = BuildNote.objects.create(
            build_model=build_model, note="hello world"
        )

        deleted = BuildNote.remove(build_model)

        self.assertIs(deleted, True)

        with self.assertRaises(BuildNote.DoesNotExist):
            build_note.refresh_from_db()


class BuildLogTestCase(TempHomeMixin, TestCase):
    """Unit tests for the BuildLog model"""

    def test_upsert_saves_note_text(self):
        build_model = BuildModelFactory.create()
        logs = "This is\na test"

        build_log = BuildLog.upsert(build_model, logs)

        self.assertEqual(build_log.logs, logs)

    def test_remove_method_returns_false_when_no_log_exists(self):
        build_model = BuildModelFactory.create()

        deleted = BuildLog.remove(build_model)

        self.assertIs(deleted, False)

    def test_remove_method_returns_true_when_log_exists(self):
        build_model = BuildModelFactory.create()
        build_log = BuildLog.objects.create(build_model=build_model, logs="hello world")

        deleted = BuildLog.remove(build_model)

        self.assertIs(deleted, True)

        with self.assertRaises(BuildLog.DoesNotExist):
            build_log.refresh_from_db()
