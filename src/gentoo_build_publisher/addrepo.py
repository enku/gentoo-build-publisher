"""Add a an ebuild repo to Jenkins

This adds an ebuild repo to Jenkins that can be used by machine builds.
"""
import argparse

from gbpcli import GBP, Console
from gbpcli.graphql import check


def handler(args: argparse.Namespace, gbp: GBP, console: Console) -> int:
    """Add a an ebuild repo to Jenkins"""
    # NOTE: This was unintentional, but ^ GBP can only see the queries for the "gbpcli"
    # distribution.  It needs a collector like gentoo-build-publisher has a collector
    # for schemas
    gbp.query._distribution = (  # pylint: disable=protected-access
        "gentoo_build_publisher"
    )

    response = check(
        gbp.query.create_repo(name=args.name, repo=args.repo, branch=args.branch)
    )

    if error := response["createRepo"]:
        console.err.print(f"error: {error['message']}")
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
