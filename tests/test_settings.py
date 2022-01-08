"""Tests for GBP Settings"""
# pylint: disable=missing-class-docstring,missing-function-docstring
from pathlib import Path
from unittest import TestCase

from gentoo_build_publisher.settings import Settings


class SettingsTestCase(TestCase):
    def test_from_dict(self):
        data_dict = dict(
            BUILD_PUBLISHER_JENKINS_USER="fail",
            TODAY_STORAGE_PATH="/home/today",
            TODAY_IS="your birthday",
            TODAY_JENKINS_BASE_URL="https://jenkins.invalid/",
        )
        prefix = "TODAY_"

        settings = Settings.from_dict(prefix, data_dict)

        self.assertEqual(settings.STORAGE_PATH, Path("/home/today"))
        self.assertEqual(
            settings.JENKINS_USER, Settings.__fields__["JENKINS_USER"].default
        )

        with self.assertRaises(AttributeError):
            settings.IS  # pylint: disable=no-member,pointless-statement

    def test_init_with_invalid_value(self):
        """Should raise ValueError when given setting not defined in DEFAULTS"""
        with self.assertRaises(ValueError):
            Settings(foo="bar")
