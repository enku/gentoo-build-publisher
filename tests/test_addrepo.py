"""Tests for the gbpcli "addrepo" subcommand"""
# pylint: disable=missing-docstring
import io
from argparse import ArgumentParser, Namespace
from typing import Any, Optional
from unittest import mock

from gbpcli import GBP
from rich.console import Console

from gentoo_build_publisher import addrepo
from gentoo_build_publisher.jenkins import ProjectPath

from . import TestCase, graphql

mock_stderr = mock.patch(
    "gentoo_build_publisher.addrepo.sys.stderr", new_callable=io.StringIO
)


def query(query_: str, variables: Optional[dict[str, Any]] = None) -> Any:
    response = graphql(query_, variables)

    return response.get("data"), response.get("errors")


class AddRepoTestCase(TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.console = mock.MagicMock(spec=Console)
        self.gbp = GBP("http://gbp.invalid/")

    def test_calls_grapql_with_the_expected_args(self) -> None:
        args = Namespace(
            name="gentoo",
            repo="https://anongit.gentoo.org/git/repo/gentoo.git",
            branch="master",
        )
        with mock.patch.object(self.gbp, "query", side_effect=query) as mock_query:
            exit_status = addrepo.handler(args, self.gbp, self.console)

        self.assertEqual(exit_status, 0)
        mock_query.assert_called_once_with(
            addrepo.GRAPHQL_QUERY,
            {
                "name": "gentoo",
                "repo": "https://anongit.gentoo.org/git/repo/gentoo.git",
                "branch": "master",
            },
        )

    @mock_stderr
    def test_when_item_already_exists(self, stderr: io.StringIO) -> None:
        self.publisher.jenkins.make_folder(ProjectPath("repos"))
        self.publisher.jenkins.create_repo_job("gentoo", "foo", "master")

        args = Namespace(
            name="gentoo",
            repo="https://anongit.gentoo.org/git/repo/gentoo.git",
            branch="master",
        )
        with mock.patch.object(self.gbp, "query", side_effect=query):
            exit_status = addrepo.handler(args, self.gbp, self.console)

        self.assertEqual(exit_status, 1)
        self.assertEqual(stderr.getvalue(), "error: FileExistsError: repos/gentoo\n")


class CheckParseArgs(TestCase):
    """Tests for the parse_args callback"""

    def test(self) -> None:
        parser = ArgumentParser()
        addrepo.parse_args(parser)
