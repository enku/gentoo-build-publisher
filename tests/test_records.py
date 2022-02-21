"""Tests for the db module"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from django.test import TestCase

from gentoo_build_publisher.types import BuildID

from .factories import BuildRecordFactory


class BuildRecordTestCase(TestCase):
    def setUp(self):
        super().setUp()

        self.record = BuildRecordFactory()

    def test_id_property(self):
        self.assertTrue(isinstance(self.record.id, BuildID))

        # pylint: disable=protected-access
        self.assertEqual(self.record.id, self.record._build_id)

    def test_repr_buildrecord(self):
        self.assertEqual(repr(self.record), f"BuildRecord(build_id='{self.record.id}')")
