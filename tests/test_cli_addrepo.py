"""Tests for the gbpcli "addrepo" subcommand"""

# pylint: disable=missing-docstring
from argparse import ArgumentParser, Namespace

from gbp_testkit import DjangoTestCase as TestCase
from unittest_fixtures import requires

from gentoo_build_publisher.build_publisher import BuildPublisher
from gentoo_build_publisher.cli import addrepo
from gentoo_build_publisher.jenkins import ProjectPath
from gentoo_build_publisher.types import EbuildRepo


@requires("publisher", "gbp", "console")
class AddRepoTestCase(TestCase):
    def test_calls_grapql_with_the_expected_args(self) -> None:
        args = Namespace(
            name="gentoo",
            repo="https://anongit.gentoo.org/git/repo/gentoo.git",
            branch="master",
        )
        console = self.fixtures.console
        exit_status = addrepo.handler(args, self.fixtures.gbp, console)

        self.assertEqual(exit_status, 0)

    def test_when_item_already_exists(self) -> None:
        publisher: BuildPublisher = self.fixtures.publisher
        publisher.jenkins.make_folder(ProjectPath("repos"))
        publisher.jenkins.create_repo_job(
            EbuildRepo(name="gentoo", url="foo", branch="master")
        )

        args = Namespace(
            name="gentoo",
            repo="https://anongit.gentoo.org/git/repo/gentoo.git",
            branch="master",
        )
        console = self.fixtures.console
        exit_status = addrepo.handler(args, self.fixtures.gbp, console)

        self.assertEqual(exit_status, 1)
        self.assertEqual(
            console.err.file.getvalue(), "error: FileExistsError: repos/gentoo\n"
        )


class CheckParseArgs(TestCase):
    """Tests for the parse_args callback"""

    def test(self) -> None:
        parser = ArgumentParser()
        addrepo.parse_args(parser)
