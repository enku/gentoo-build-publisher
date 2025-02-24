"""Delete a build"""

import argparse

from gbpcli.gbp import GBP
from gbpcli.subcommands import completers as comp
from gbpcli.types import Console

from gentoo_build_publisher import publisher
from gentoo_build_publisher.settings import Settings
from gentoo_build_publisher.types import Build

HELP = "Delete the given build" ""


def handler(args: argparse.Namespace, _gbp: GBP, console: Console) -> int:
    """Delete the given build"""
    build = Build(args.machine, args.number)
    tags = ([""] if publisher.published(build) else []) + publisher.tags(build)

    if tags and not args.force:
        tag_type = "published" if "" in tags else "tagged"
        console.err.print(f"Cannot delete a {tag_type} build.")
        return 1

    for tag in tags:
        publisher.untag(build.machine, tag)
    publisher.delete(build)

    return 0


# pylint: disable=duplicate-code
def parse_args(parser: argparse.ArgumentParser) -> None:
    """Set subcommand arguments"""
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        default=False,
        help="Force delete published and/or tagged build",
    )
    comp.set(
        parser.add_argument("machine", metavar="MACHINE", help="name of the machine"),
        comp.machines,
    )
    comp.set(
        parser.add_argument("number", metavar="NUMBER", help="build number"),
        comp.build_ids,
    )
