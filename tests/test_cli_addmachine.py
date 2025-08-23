"""Tests for the gbpcli "addmachine" subcommand"""

# pylint: disable=missing-docstring
from argparse import ArgumentParser
from unittest import mock

from unittest_fixtures import Fixtures, given

import gbp_testkit.fixtures as testkit
from gbp_testkit import DjangoTestCase as TestCase
from gentoo_build_publisher import publisher
from gentoo_build_publisher.cli import addmachine
from gentoo_build_publisher.types import MachineJob, Repo


@given(testkit.gbpcli)
class AddMachineTestCase(TestCase):
    def test_calls_jenkins_with_the_expected_args(self, fixtures: Fixtures) -> None:
        # Given the command-line args
        cmdline = "gbp addmachine base https://github.com/enku/gbp-machines.git"

        # When we call the addmachine handler
        exit_status = fixtures.gbpcli(cmdline)

        # Then it calls Jenkins with the expected args
        self.assertEqual(exit_status, 0)
        jenkins = publisher.jenkins
        jenkins.session.post.assert_called_with(
            "https://jenkins.invalid/createItem",
            data=mock.ANY,
            headers={"Content-Type": "text/xml"},
            params={"name": "base"},
        )
        data = jenkins.session.post.call_args[1]["data"]
        self.assertIn(
            "<url>https://github.com/enku/gbp-machines.git</url>",
            data,
            "machine repo not found in post data",
        )
        self.assertIn("<name>*/master</name>", data, "branch not found in post data")
        self.assertIn(
            "<upstreamProjects>repos/gentoo</upstreamProjects>",
            data,
            "ebuild repo not found in post data",
        )

    def test_when_item_already_exists(self, fixtures: Fixtures) -> None:
        job = MachineJob(
            name="base",
            repo=Repo(url="https://github.com/enku/gbp-machines.git", branch="master"),
            ebuild_repos=["gentoo"],
        )
        publisher.jenkins.create_machine_job(job)

        cmdline = "gbp addmachine base https://github.com/enku/gbp-machines.git"
        exit_status = fixtures.gbpcli(cmdline)

        self.assertEqual(exit_status, 1)
        self.assertEqual(fixtures.console.stderr, "error: FileExistsError: base\n")


class CheckParseArgs(TestCase):
    """Tests for the parse_args callback"""

    def test(self) -> None:
        parser = ArgumentParser()
        addmachine.parse_args(parser)
