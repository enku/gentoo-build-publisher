"""Add a an ebuild repo to Jenkins

This adds an ebuild repo to Jenkins that can be used by machine builds.
"""
import argparse
import sys
from typing import TextIO

from gbpcli import GBP
from rich.console import Console

GRAPHQL_QUERY = """\
mutation ($name: String!, $repo: String!, $branch: String!) {
 createRepo(name: $name, repo: $repo, branch: $branch) {
    message
  }
}
"""


def handler(
    args: argparse.Namespace, gbp: GBP, _console: Console, errorf: TextIO = sys.stderr
) -> int:
    """Add a an ebuild repo to Jenkins"""
    query_vars = {"name": args.name, "repo": args.repo, "branch": args.branch}
    response = gbp.check(GRAPHQL_QUERY, query_vars)

    if error := response["createRepo"]:
        print(f"error: {error['message']}", file=errorf)

        return 1

    return 0


def parse_args(parser: argparse.ArgumentParser) -> None:
    """Set subcommand arguments"""
    name_help = 'The name for the repo (e.g. "gentoo" or the overlay\'s name"'
    parser.add_argument("name", type=str, metavar="NAME", help=name_help)

    repo_help = "(git) URL for the ebuild repo"
    parser.add_argument("repo", type=str, metavar="REPO", help=repo_help)

    branch_help = "git branch to pull from (default: master)"
    parser.add_argument(
        "--branch", type=str, metavar="BRANCH", default="master", help=branch_help
    )
