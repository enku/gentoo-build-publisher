"""Unit tests for gbp models"""

# pylint: disable=missing-class-docstring,missing-function-docstring
from gentoo_build_publisher.models import BuildLog, BuildNote, KeptBuild

from . import DjangoTestCase as TestCase
from .factories import BuildModelFactory


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
