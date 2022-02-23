"""Tests for the db module"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from django.test import TestCase

from .factories import BuildRecordFactory


class BuildRecordTestCase(TestCase):
    def setUp(self):
        super().setUp()

        self.record = BuildRecordFactory()

    def test_repr_buildrecord(self):
        self.assertEqual(repr(self.record), f"BuildRecord('{self.record}')")
