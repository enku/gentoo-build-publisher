"""Add a an ebuild repo to Jenkins

This adds an ebuild repo to Jenkins that can be used by machine builds.
"""
import argparse

from gbpcli import GBP, Console
from gbpcli.graphql import Query, check


def handler(args: argparse.Namespace, gbp: GBP, console: Console) -> int:
    """Add a an ebuild repo to Jenkins"""
    create_machine: Query
    if hasattr(gbp.query, "_distribution"):
        # Older GBP can only see the queries for the "gbpcli" distribution and need to
        # be overridden to see queries from other distributions
        gbp.query._distribution = (  # pylint: disable=protected-access
            "gentoo_build_publisher"
        )
        create_machine = gbp.query.create_machine
    else:
        create_machine = (
            gbp.query.gentoo_build_publisher.create_machine  # type: ignore[attr-defined]
        )

    response = check(
        create_machine(
            branch=args.branch, ebuildRepos=args.deps, name=args.name, repo=args.repo
        )
    )

    if error := response["createMachine"]:
        console.err.print(f"error: {error['message']}")
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
