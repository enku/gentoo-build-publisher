"""Unit tests for gbp models"""
from django.test import TestCase

from gentoo_build_publisher import Jenkins, Settings, Storage
from gentoo_build_publisher.models import KeptBuild

from . import MockJenkins, TempHomeMixin
from .factories import BuildModelFactory


class BuildModelTestCase(TempHomeMixin, TestCase):
    """Unit tests for the BuildModel"""

    def test_as_dict(self):
        """build.as_dict() should return the expected dict"""
        settings = Settings(
            JENKINS_ARTIFACT_NAME="build.tar.gz",
            JENKINS_BASE_URL="http://jenkins.invalid/job/Gentoo",
        )
        jenkins = Jenkins.from_settings(settings)

        build_model = BuildModelFactory.create(
            storage=Storage(self.tmpdir), jenkins=jenkins
        )

        as_dict = build_model.as_dict()

        expected = {
            "name": build_model.name,
            "number": build_model.number,
            "published": False,
            "url": (
                "http://jenkins.invalid/job/Gentoo/job/"
                f"{build_model.name}/{build_model.number}/artifact/build.tar.gz"
            ),
        }
        self.assertEqual(as_dict, expected)

    def test_publish(self):
        """.publish should publish the build artifact"""
        settings = Settings(
            HOME_DIR=self.tmpdir,
            JENKINS_ARTIFACT_NAME="build.tar.gz",
            JENKINS_BASE_URL="http://jenkins.invalid/job/Gentoo",
        )
        jenkins = MockJenkins.from_settings(settings)

        build_model = BuildModelFactory.create(settings=settings, jenkins=jenkins)

        build_model.publish()

        storage = Storage.from_settings(settings)
        self.assertIs(storage.published(build_model.build), True)

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

    def test_purge_when_keep_is_true(self):
        """When marked kept should throw an error when calling .delete()"""
        build_model = BuildModelFactory()
        KeptBuild.objects.create(build_model=build_model)

        with self.assertRaises(ValueError) as context:
            build_model.delete()

        exception = context.exception
        self.assertEqual(str(exception), "BuildModel marked kept cannot be deleted")

    def test_keep_getter_false(self):
        """.keep should be False when there is no KeptBuild for the BuildModel"""
        build_model = BuildModelFactory.create()

        self.assertIs(build_model.keep, False)

    def test_keep_getter_true(self):
        """.keep should be True when ther is a KeptBuild for the BuildModel"""
        build_model = BuildModelFactory.create()
        KeptBuild.objects.create(build_model=build_model)

        self.assertIs(build_model.keep, True)

    def test_keep_true_setter_when_no_keptbuild(self):
        """keep=True should create a KeptBuild when there isn't one"""
        build_model = BuildModelFactory.create()

        build_model.keep = True

        KeptBuild.objects.get(build_model=build_model)

    def test_keep_setter_false_when_keptbuild(self):
        """.keep=False should delete the existing KeptBuild"""
        build_model = BuildModelFactory.create()
        KeptBuild.objects.create(build_model=build_model)

        build_model.keep = False

        with self.assertRaises(KeptBuild.DoesNotExist):
            KeptBuild.objects.get(build_model=build_model)

    def test_keep_setter_false_when_not_keptbuild(self):
        build_model = BuildModelFactory.create()

        build_model.keep = False

        self.assertIs(build_model.keep, False)


class KeptBuildTestCase(TempHomeMixin, TestCase):
    """Unit tests for KeptBuild"""

    def test_str(self):
        build_model = BuildModelFactory.create()
        kept_build = KeptBuild.objects.create(build_model=build_model)

        self.assertEqual(str(kept_build), str(build_model))
