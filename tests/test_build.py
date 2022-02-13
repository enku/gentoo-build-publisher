"""Tests for the build module"""
# pylint: disable=missing-docstring
from unittest import TestCase

from gentoo_build_publisher.build import BuildID, InvalidBuildID


class BuildIDTestCase(TestCase):
    def test_string_with_name_and_number(self):
        build_id = BuildID("babette.16")

        self.assertEqual(build_id, "babette.16")

    def test_string_with_invalid_number(self):
        with self.assertRaises(InvalidBuildID):
            BuildID("babette.16f")

    def test_string_with_no_name(self):
        with self.assertRaises(InvalidBuildID):
            BuildID(".16")

    def test_has_name_and_number_attrs(self):
        build_id = BuildID("babette.16")

        self.assertEqual(build_id.name, "babette")
        self.assertEqual(build_id.number, 16)
