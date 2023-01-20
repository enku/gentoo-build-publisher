"""Tests for the db module"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from pathlib import Path

from django.test import TestCase

from gentoo_build_publisher.models import DjangoDB
from gentoo_build_publisher.records import Records
from gentoo_build_publisher.settings import Settings


class RecordsTestCase(TestCase):
    def test_from_settings_django(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            STORAGE_PATH=Path("/dev/null"),
            RECORDS_BACKEND="django",
        )

        recorddb = Records.from_settings(settings)
        self.assertIsInstance(recorddb, DjangoDB)

    def test_unknown_records_backend(self) -> None:
        settings = Settings(
            JENKINS_BASE_URL="http://jenkins.invalid/",
            STORAGE_PATH=Path("/dev/null"),
            RECORDS_BACKEND="bogus_backend",
        )

        with self.assertRaises(LookupError):
            Records.from_settings(settings)
