"""Tests for the cli delete subcommand"""

# pylint: disable=missing-docstring
from argparse import ArgumentParser, Namespace

from unittest_fixtures import Fixtures, fixture, given, where

from gbp_testkit import TestCase
from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import delete
from gentoo_build_publisher.types import Build


@fixture("builds")
def build_fixture(fixtures: Fixtures) -> Build:
    builds: list[Build] = fixtures.builds
    return builds[0]


@fixture(build_fixture)
def args_fixture(fixtures: Fixtures) -> Namespace:
    return Namespace(machine="babette", number=fixtures.build.build_id, force=False)


@fixture(build_fixture)
def force_args_fixture(fixtures: Fixtures) -> Namespace:
    return Namespace(machine="babette", number=fixtures.build.build_id, force=True)


@given(
    "pulled_builds", "console", "gbp", build_fixture, args_fixture, force_args_fixture
)
@where(builds__per_day=5)
class GBPChkTestCase(TestCase):
    def test_deletes_build(self, fixtures: Fixtures) -> None:
        build: Build = fixtures.build

        self.assertTrue(publisher.pulled(build))
        delete.handler(fixtures.args, fixtures.gbp, fixtures.console)

        self.assertFalse(publisher.pulled(build))

    def test_published_build(self, fixtures: Fixtures) -> None:
        build: Build = fixtures.build
        publisher.publish(build)

        status = delete.handler(fixtures.args, fixtures.gbp, fixtures.console)

        self.assertEqual(status, 1)
        stderr = fixtures.console.err.file.getvalue()
        self.assertEqual(stderr, "Cannot delete a published build.\n")
        self.assertTrue(publisher.pulled(build))

        status = delete.handler(fixtures.force_args, fixtures.gbp, fixtures.console)
        self.assertEqual(status, 0)
        self.assertFalse(publisher.pulled(build))

    def test_tagged_build(self, fixtures: Fixtures) -> None:
        build: Build = fixtures.build
        publisher.tag(build, "testing")

        status = delete.handler(fixtures.args, fixtures.gbp, fixtures.console)

        self.assertEqual(status, 1)
        stderr = fixtures.console.err.file.getvalue()
        self.assertEqual(stderr, "Cannot delete a tagged build.\n")
        self.assertTrue(publisher.pulled(build))

        status = delete.handler(fixtures.force_args, fixtures.gbp, fixtures.console)
        self.assertEqual(status, 0)
        self.assertFalse(publisher.pulled(build))


class CheckParseArgs(TestCase):
    """Tests for the parse_args callback"""

    def test(self) -> None:
        parser = ArgumentParser()
        delete.parse_args(parser)

        dests = [i.dest for i in parser._actions]  # pylint: disable=protected-access

        self.assertEqual(dests, ["help", "force", "machine", "number"])
