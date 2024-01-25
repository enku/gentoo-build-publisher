"""Tests for the gbpcli "addrepo" subcommand"""
# pylint: disable=missing-docstring
from argparse import ArgumentParser, Namespace

from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import addrepo
from gentoo_build_publisher.common import EbuildRepo
from gentoo_build_publisher.jenkins import ProjectPath

from . import TestCase, string_console, test_gbp


class AddRepoTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.gbp = test_gbp("http://gbp.invalid/")

    def test_calls_grapql_with_the_expected_args(self) -> None:
        args = Namespace(
            name="gentoo",
            repo="https://anongit.gentoo.org/git/repo/gentoo.git",
            branch="master",
        )
        console = string_console()[0]
        exit_status = addrepo.handler(args, self.gbp, console)

        self.assertEqual(exit_status, 0)

    def test_when_item_already_exists(self) -> None:
        publisher.jenkins.make_folder(ProjectPath("repos"))
        publisher.jenkins.create_repo_job(
            EbuildRepo(name="gentoo", url="foo", branch="master")
        )

        args = Namespace(
            name="gentoo",
            repo="https://anongit.gentoo.org/git/repo/gentoo.git",
            branch="master",
        )
        console, _, err = string_console()
        exit_status = addrepo.handler(args, self.gbp, console)

        self.assertEqual(exit_status, 1)
        self.assertEqual(err.getvalue(), "error: FileExistsError: repos/gentoo\n")


class CheckParseArgs(TestCase):
    """Tests for the parse_args callback"""

    def test(self) -> None:
        parser = ArgumentParser()
        addrepo.parse_args(parser)
