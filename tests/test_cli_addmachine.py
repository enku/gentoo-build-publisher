"""Tests for the gbpcli "addmachine" subcommand"""

# pylint: disable=missing-docstring,attribute-defined-outside-init
from argparse import ArgumentParser, Namespace

from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import addmachine
from gentoo_build_publisher.types import MachineJob, Repo

from . import DjangoTestCase as TestCase
from . import string_console


class AddMachineTestCase(TestCase):

    requires = ["publisher", "gbp"]

    def test_calls_grapql_with_the_expected_args(self) -> None:
        args = Namespace(
            name="base",
            repo="https://github.com/enku/gbp-machines.git",
            branch="master",
            deps=["gentoo"],
        )
        console = string_console()[0]
        exit_status = addmachine.handler(args, self.fixtures.gbp, console)

        self.assertEqual(exit_status, 0)

    def test_when_item_already_exists(self) -> None:
        job = MachineJob(
            name="base",
            repo=Repo(url="https://github.com/enku/gbp-machines.git", branch="master"),
            ebuild_repos=["gentoo"],
        )
        publisher.jenkins.create_machine_job(job)

        args = Namespace(
            name="base",
            repo="https://github.com/enku/gbp-machines.git",
            branch="master",
            deps=["gentoo"],
        )
        console, _, err = string_console()
        exit_status = addmachine.handler(args, self.fixtures.gbp, console)

        self.assertEqual(exit_status, 1)
        self.assertEqual(err.getvalue(), "error: FileExistsError: base\n")


class CheckParseArgs(TestCase):
    """Tests for the parse_args callback"""

    def test(self) -> None:
        parser = ArgumentParser()
        addmachine.parse_args(parser)
