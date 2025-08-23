"""Tests for the gbpcli "addrepo" subcommand"""

# pylint: disable=missing-docstring
from argparse import ArgumentParser

from unittest_fixtures import Fixtures, given

import gbp_testkit.fixtures as testkit
from gbp_testkit import DjangoTestCase as TestCase
from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import addrepo
from gentoo_build_publisher.jenkins import ProjectPath
from gentoo_build_publisher.types import EbuildRepo


@given(testkit.publisher, testkit.gbpcli)
class AddRepoTestCase(TestCase):
    def test_calls_graphql_with_the_expected_args(self, fixtures: Fixtures) -> None:
        cmdline = (
            "gbp addrepo"
            " --branch=master gentoo https://github.com/gentoo-mirror/gentoo.git"
        )
        exit_status = fixtures.gbpcli(cmdline)

        self.assertEqual(exit_status, 0)

    def test_when_item_already_exists(self, fixtures: Fixtures) -> None:
        publisher.jenkins.make_folder(ProjectPath("repos"))
        publisher.jenkins.create_repo_job(
            EbuildRepo(name="gentoo", url="foo", branch="master")
        )

        cmdline = (
            "gbp addrepo"
            " --branch=master gentoo https://github.com/gentoo-mirror/gentoo.git"
        )
        exit_status = fixtures.gbpcli(cmdline)

        self.assertEqual(exit_status, 1)
        self.assertEqual(
            fixtures.console.stderr, "error: FileExistsError: repos/gentoo\n"
        )


class CheckParseArgs(TestCase):
    """Tests for the parse_args callback"""

    def test(self) -> None:
        parser = ArgumentParser()
        addrepo.parse_args(parser)
