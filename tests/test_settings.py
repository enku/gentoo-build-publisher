"""Tests for GBP Settings"""
from unittest import TestCase

from gentoo_build_publisher import Settings


class SettingsTestCase(TestCase):
    def test_from_dict(self):
        data_dict = dict(
            BUILD_PUBLISHER_JENKINS_USER="fail",
            TODAY_HOME_DIR="/home/today",
            TODAY_IS="your birthday",
        )
        prefix = "TODAY_"

        settings = Settings.from_dict(prefix, data_dict)

        self.assertEqual(settings.HOME_DIR, "/home/today")
        self.assertEqual(settings.JENKINS_USER, Settings.DEFAULTS["JENKINS_USER"])

        with self.assertRaises(AttributeError):
            settings.IS
