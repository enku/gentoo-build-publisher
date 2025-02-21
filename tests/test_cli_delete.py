"""Tests for the cli delete subcommand"""

# pylint: disable=missing-docstring
from argparse import ArgumentParser, Namespace
from typing import Any

from gbp_testkit import TestCase
from unittest_fixtures import Fixtures, fixture, given, where

from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import delete
from gentoo_build_publisher.types import Build


@fixture("builds")
def build_fixture(_options: Any, fixtures: Fixtures) -> Build:
    builds: list[Build] = fixtures.builds
    return builds[0]


@fixture(build_fixture)
def args_fixture(_options: Any, fixtures: Fixtures) -> Namespace:
    return Namespace(machine="babette", number=fixtures.build.build_id, force=False)


@fixture(build_fixture)
def force_args_fixture(_options: Any, fixtures: Fixtures) -> Namespace:
    return Namespace(machine="babette", number=fixtures.build.build_id, force=True)


@given(
    "pulled_builds", "console", "gbp", build_fixture, args_fixture, force_args_fixture
)
@where(builds={"per_day": 5}, environ={"BUILD_PUBLISHER_MANUAL_DELETE_ENABLE": "true"})
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


@given("pulled_builds", "console", "gbp", build_fixture, args_fixture)
class DisabledDeletestTests(TestCase):
    options = {"environ": {"BUILD_PUBLISHER_MANUAL_DELETE_ENABLE": "false"}}

    def test_deletes_disabled(self, fixtures: Fixtures) -> None:
        build: Build = fixtures.build
        console = fixtures.console

        status = delete.handler(fixtures.args, fixtures.gbp, console)

        self.assertEqual(status, 1)
        stderr = console.err.file.getvalue()
        self.assertEqual(
            stderr, "Cannot delete builds because this feature is disabled.\n"
        )
        self.assertTrue(publisher.pulled(build))


class CheckParseArgs(TestCase):
    """Tests for the parse_args callback"""

    def test(self) -> None:
        parser = ArgumentParser()
        delete.parse_args(parser)

        dests = [i.dest for i in parser._actions]  # pylint: disable=protected-access

        self.assertEqual(dests, ["help", "force", "machine", "number"])
