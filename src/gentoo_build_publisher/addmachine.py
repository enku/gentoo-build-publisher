"""Add a an ebuild repo to Jenkins

This adds an ebuild repo to Jenkins that can be used by machine builds.
"""
import argparse
import sys
from typing import TextIO

from gbpcli import GBP
from rich.console import Console

GRAPHQL_QUERY = """\
mutation ($name: String!, $repo: String!, $branch: String!, $ebuildRepos: [String!]!) {
 createMachine(name: $name, repo: $repo, branch: $branch, ebuildRepos: $ebuildRepos) {
    message
  }
}
"""


def handler(
    args: argparse.Namespace, gbp: GBP, _console: Console, errorf: TextIO = sys.stderr
) -> int:
    """Add a an ebuild repo to Jenkins"""
    query_vars = {
        "branch": args.branch,
        "ebuildRepos": args.deps,
        "name": args.name,
        "repo": args.repo,
    }
    response = gbp.check(GRAPHQL_QUERY, query_vars)

    if error := response["createMachine"]:
        print(f"error: {error['message']}", file=errorf)

        return 1

    return 0


def parse_args(parser: argparse.ArgumentParser) -> None:
    """Set subcommand arguments"""
    name_help = "The name of the machine"
    parser.add_argument("name", type=str, metavar="NAME", help=name_help)

    repo_help = "(git) URL that contains the machine's pipeline script"
    parser.add_argument("repo", type=str, metavar="REPO", help=repo_help)

    branch_help = "git branch to pull from (default: master)"
    parser.add_argument(
        "--branch", type=str, metavar="BRANCH", default="master", help=branch_help
    )

    deps_help = "List of ebuild repos the machine depends on (default: gentoo)"
    parser.add_argument(
        "--deps",
        "-d",
        type=str,
        metavar="DEPS",
        default=["gentoo"],
        help=deps_help,
        nargs="*",
    )
