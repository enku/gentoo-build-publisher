"""Tests for the gbpcli "addmachine" subcommand"""
# pylint: disable=missing-docstring
import io
from argparse import ArgumentParser, Namespace
from typing import Any
from unittest import mock

from gbpcli import GBP
from rich.console import Console

from gentoo_build_publisher import addmachine

from . import TestCase, graphql

mock_stderr = mock.patch(
    "gentoo_build_publisher.addmachine.sys.stderr", new_callable=io.StringIO
)


def query(query_: str, variables: dict[str, Any] | None = None) -> Any:
    response = graphql(query_, variables)

    return response.get("data"), response.get("errors")


class AddMachineTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.console = mock.MagicMock(spec=Console)
        self.gbp = GBP("http://gbp.invalid/")

    def test_calls_grapql_with_the_expected_args(self) -> None:
        args = Namespace(
            name="base",
            repo="https://github.com/enku/gbp-machines.git",
            branch="master",
            deps=["gentoo"],
        )
        with mock.patch.object(self.gbp, "query", side_effect=query) as mock_query:
            exit_status = addmachine.handler(args, self.gbp, self.console)

        self.assertEqual(exit_status, 0)
        mock_query.assert_called_once_with(
            addmachine.GRAPHQL_QUERY,
            {
                "name": "base",
                "repo": "https://github.com/enku/gbp-machines.git",
                "branch": "master",
                "ebuildRepos": ["gentoo"],
            },
        )

    @mock_stderr
    def test_when_item_already_exists(self, stderr: io.StringIO) -> None:
        self.publisher.jenkins.create_machine_job(
            "base", "https://github.com/enku/gbp-machines.git", "master", ["gentoo"]
        )

        args = Namespace(
            name="base",
            repo="https://github.com/enku/gbp-machines.git",
            branch="master",
            deps=["gentoo"],
        )
        with mock.patch.object(self.gbp, "query", side_effect=query):
            exit_status = addmachine.handler(args, self.gbp, self.console)

        self.assertEqual(exit_status, 1)
        self.assertEqual(stderr.getvalue(), "error: FileExistsError: base\n")


class CheckParseArgs(TestCase):
    """Tests for the parse_args callback"""

    def test(self) -> None:
        parser = ArgumentParser()
        addmachine.parse_args(parser)
