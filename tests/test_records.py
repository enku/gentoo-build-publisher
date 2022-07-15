"""Tests for the db module"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from pathlib import Path

from django.test import TestCase

from gentoo_build_publisher.models import RecordDB
from gentoo_build_publisher.records import Records
from gentoo_build_publisher.settings import Settings

from .factories import BuildRecordFactory


class BuildRecordTestCase(TestCase):
    def setUp(self):
        super().setUp()

        self.record = BuildRecordFactory()

    def test_repr_buildrecord(self):
        self.assertEqual(repr(self.record), f"BuildRecord('{self.record}')")


class RecordsTestCase(TestCase):
    def test_from_settings_django(self):
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            STORAGE_PATH=Path("/dev/null"),
            RECORDS_BACKEND="django",
        )

        recorddb = Records.from_settings(settings)
        self.assertIsInstance(recorddb, RecordDB)

    def test_unknown_records_backend(self):
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            STORAGE_PATH=Path("/dev/null"),
            RECORDS_BACKEND="bogus_backend",
        )

        with self.assertRaises(LookupError):
            Records.from_settings(settings)
