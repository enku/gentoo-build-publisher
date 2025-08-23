"""Tests for the cli delete subcommand"""

# pylint: disable=missing-docstring
from argparse import ArgumentParser

from unittest_fixtures import Fixtures, fixture, given, where

import gbp_testkit.fixtures as testkit
from gbp_testkit import TestCase
from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import delete
from gentoo_build_publisher.types import Build


@fixture(testkit.builds)
def build_fixture(fixtures: Fixtures) -> Build:
    builds: list[Build] = fixtures.builds
    return builds[0]


@given(testkit.gbpcli, testkit.pulled_builds, build_fixture)
@where(builds__per_day=5)
class GBPChkTestCase(TestCase):
    def test_deletes_build(self, fixtures: Fixtures) -> None:
        build: Build = fixtures.build

        self.assertTrue(publisher.pulled(build))
        fixtures.gbpcli(f"gbp delete {build.machine} {build.build_id}")

        self.assertFalse(publisher.pulled(build))

    def test_published_build(self, fixtures: Fixtures) -> None:
        build: Build = fixtures.build
        publisher.publish(build)

        status = fixtures.gbpcli(f"gbp delete {build.machine} {build.build_id}")

        self.assertEqual(status, 1)
        stderr = fixtures.console.stderr
        self.assertEqual(stderr, "Cannot delete a published build.\n")
        self.assertTrue(publisher.pulled(build))

        status = fixtures.gbpcli(f"gbp delete -f {build.machine} {build.build_id}")
        self.assertEqual(status, 0)
        self.assertFalse(publisher.pulled(build))

    def test_tagged_build(self, fixtures: Fixtures) -> None:
        build: Build = fixtures.build
        publisher.tag(build, "testing")

        status = fixtures.gbpcli(f"gbp delete {build.machine} {build.build_id}")

        self.assertEqual(status, 1)
        stderr = fixtures.console.stderr
        self.assertEqual(stderr, "Cannot delete a tagged build.\n")
        self.assertTrue(publisher.pulled(build))

        status = fixtures.gbpcli(f"gbp delete -f {build.machine} {build.build_id}")
        self.assertEqual(status, 0)
        self.assertFalse(publisher.pulled(build))


class CheckParseArgs(TestCase):
    """Tests for the parse_args callback"""

    def test(self) -> None:
        parser = ArgumentParser()
        delete.parse_args(parser)

        dests = [i.dest for i in parser._actions]  # pylint: disable=protected-access

        self.assertEqual(dests, ["help", "force", "machine", "number"])
