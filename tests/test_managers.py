"""Tests for GBP managers"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from django.test import TestCase

from . import TempHomeMixin
from .factories import BuildManFactory


class BuildManTestCase(TempHomeMixin, TestCase):
    def test_as_dict(self):
        """build.as_dict() should return the expected dict"""
        buildman = BuildManFactory.build()

        as_dict = buildman.as_dict()

        expected = {
            "name": buildman.name,
            "note": None,
            "number": buildman.number,
            "published": False,
            "submitted": buildman.db.submitted.isoformat(),
            "completed": None,
            "url": (
                "https://jenkins.invalid/job/"
                f"{buildman.name}/{buildman.number}/artifact/build.tar.gz"
            ),
        }
        self.assertEqual(as_dict, expected)

    def test_as_dict_with_buildnote(self):
        buildman = BuildManFactory.build()
        buildman.db.note = "This is a test"
        buildman.db.save()

        as_dict = buildman.as_dict()

        expected = {
            "name": buildman.name,
            "note": "This is a test",
            "number": buildman.number,
            "published": False,
            "submitted": buildman.db.submitted.isoformat(),
            "completed": None,
            "url": (
                "https://jenkins.invalid/job/"
                f"{buildman.name}/{buildman.number}/artifact/build.tar.gz"
            ),
        }
        self.assertEqual(as_dict, expected)

    def test_publish(self):
        """.publish should publish the build artifact"""
        buildman = BuildManFactory.build()

        buildman.publish()

        self.assertIs(buildman.storage_build.published(), True)
