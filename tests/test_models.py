"""Unit tests for gbp models"""
import datetime
from unittest import mock

from django.test import TestCase
from django.utils.timezone import make_aware

from gentoo_build_publisher import Jenkins, Settings, Storage
from gentoo_build_publisher.models import BuildModel

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
