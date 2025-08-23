"""Tests for gbp_testkit.helpers"""

# pylint: disable=missing-docstring
from unittest import TestCase

from unittest_fixtures import Fixtures, given

import gbp_testkit.fixtures as testkit
from gbp_testkit.helpers import print_command


@given(testkit.console)
class PrintCommandTests(TestCase):
    def test(self, fixtures: Fixtures) -> None:
        console = fixtures.console
        cmdline = "rm -rf /"
        print_command(cmdline, console)

        self.assertEqual("$ rm -rf /\n", console.stdout)
