"""Tests for GBP managers"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from django.test import TestCase

from gentoo_build_publisher.build import Build
from gentoo_build_publisher.managers import BuildMan
from gentoo_build_publisher.settings import Settings

from . import TempHomeMixin
from .factories import BuildManFactory, MockJenkinsBuild


class BuildManTestCase(TempHomeMixin, TestCase):
    def test_as_dict(self):
        """build.as_dict() should return the expected dict"""
        buildman = BuildManFactory.build()
        buildman.db.keep = True
        buildman.db.save()

        as_dict = buildman.as_dict()

        expected = {
            "name": buildman.name,
            "number": buildman.number,
            "db": {
                "note": None,
                "keep": True,
                "submitted": buildman.db.submitted.isoformat(),
                "completed": None,
            },
            "storage": {
                "published": False,
                "pulled": False,
            },
            "jenkins": {
                "url": (
                    "https://jenkins.invalid/job/"
                    f"{buildman.name}/{buildman.number}/artifact/build.tar.gz"
                ),
            }
        }
        self.assertEqual(as_dict, expected)

    def test_as_dict_with_buildnote(self):
        buildman = BuildManFactory.build()
        buildman.db.note = "This is a test"
        buildman.db.save()

        as_dict = buildman.as_dict()

        expected = {
            "name": buildman.name,
            "number": buildman.number,
            "db": {
                "note": "This is a test",
                "completed": None,
                "submitted": buildman.db.submitted.isoformat(),
                "keep": False,
            },
            "jenkins": {
                "url": (
                    "https://jenkins.invalid/job/"
                    f"{buildman.name}/{buildman.number}/artifact/build.tar.gz"
                ),
            },
            "storage": {
                "published": False,
                "pulled": False,
            }
        }
        self.assertEqual(as_dict, expected)

    def test_publish(self):
        """.publish should publish the build artifact"""
        buildman = BuildManFactory.build()

        buildman.publish()

        self.assertIs(buildman.storage_build.published(), True)

    def test_pull_without_db(self):
        """pull creates db instance and pulls from jenkins"""
        build = Build(name="babette", number=193)
        settings = Settings.from_environ()
        jenkins_build = MockJenkinsBuild.from_settings(build, settings)
        buildman = BuildMan(build, jenkins_build=jenkins_build)

        buildman.pull()

        self.assertIs(buildman.storage_build.pulled(), True)
        self.assertIsNot(buildman.db, None)
