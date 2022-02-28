"""Tests for the types module"""
# pylint: disable=missing-docstring
from unittest import TestCase

from gentoo_build_publisher.types import Build, InvalidBuild


class BuildTestCase(TestCase):
    def test_string_with_name_and_number(self):
        build = Build("babette.16")

        self.assertEqual(str(build), "babette.16")

    def test_string_with_no_name(self):
        with self.assertRaises(InvalidBuild):
            Build(".16")

    def test_has_machine_and_build_id_attrs(self):
        build = Build("babette.16")

        self.assertEqual(build.machine, "babette")
        self.assertEqual(build.build_id, "16")

    def test_repr(self):
        build = Build("babette.16")

        self.assertEqual("Build('babette.16')", repr(build))
